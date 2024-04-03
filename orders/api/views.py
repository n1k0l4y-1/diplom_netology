import json
from distutils.util import strtobool

import requests
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import URLValidator
from django.db import IntegrityError
from django.db.models import Sum, F, Q
from django.http import JsonResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.authtoken.models import Token
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from yaml import load as load_yaml, Loader

from .models import User, Order, OrderItem, Contact, ConfirmEmailToken, Category, Shop, ProductInfo, ProductParameter, \
    Parameter, Product
from .permissions import IsShopUser
from .serializers import UserSerializer, ContactSerializer, OrderSerializer, OrderItemSerializer, ShopSerializer, \
    CategorySerializer, ProductInfoSerializer


class RegisterAccount(APIView):
    """
    Класс регистрации покупателей.
    """

    def post(self, request, *args, **kwargs):

        """
        Проверка наличия полей на уникальность и сложность пароля.
        """

        if {'first_name', 'last_name', 'email', 'password', 'company', 'position'}.issubset(request.data):
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = []
                for item in password_error:
                    error_array.append(item)
                return Response({'Status': False, 'Errors': {'password': error_array}}, status=403)
            else:
                request.data._mutable = True
                request.data.update({})
                user_serializer = UserSerializer(data=request.data)

                if user_serializer.is_valid():
                    user = user_serializer.save()
                    user.set_password(request.data['password'])
                    user.save()

                    # Отправление на подтверждение почты.
                    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user.id)
                    title = f'Регистрация пользователя подтверждена: {token.user.email}'  #

                    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user.pk)

                    msg = EmailMultiAlternatives(
                        # title:
                        title,
                        # message:
                        token.key,
                        # from:
                        settings.EMAIL_HOST_USER,
                        # to:
                        [user.email]
                    )
                    msg.send()

                    return Response({'Status': True}, status=201)
                else:
                    return Response({'Status': False,
                                     'Errors': user_serializer.errors}, status=422)

        return Response({'Status': False,
                         'Errors': 'Не введены все обязательные параметры'}, status=401)


class ConfirmAccount(APIView):
    """
    Класс подтверждения почтового адреса.
    """

    throttle_scope = 'anon'

    def post(self, request, *args, **kwargs):

        """
        Проверка на наличие статуса токена, обязательных полей и почты.
        """

        if {'email', 'token'}.issubset(request.data):
            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return Response({'Status': True})
            else:
                return Response({'Status': False,
                                 'Errors': 'Токен или адрес e-mail указаны неверно'})

        return Response({'Status': False,
                         'Errors': 'Отсутствуют обязательные аргументы'})


class AccountDetails(APIView):
    """
    Класс работы c данными пользователя.
    """

    throttle_scope = 'user'

    def get(self, request, *args, **kwargs):
        """
        Получение данных о пользователе.
        """

        if not request.user.is_authenticated:
            return Response({'Status': False,
                             'Error': 'Log in required'}, status=403)

        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class LoginAccount(APIView):
    """
    Класс авторизации пользователей.
    """

    throttle_scope = 'anon'

    def post(self, request, *args, **kwargs):

        """
        Произведение авторизацию пользователя.
        """

        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])
            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)
                    return Response({'Status': True, 'Token': token.key}, status=200)

            return Response({'Status': False,
                             'Errors': 'Авторизация не удалась'}, status=403)

        return Response({'Status': False,
                         'Errors': 'Отсутствуют обязательные аргументы'}, status=401)


class ContactView(APIView):
    """ Класс работы с контактами покупателей. """

    throttle_scope = 'user'

    def get(self, request, *args, **kwargs):

        """
        Проверка авторизации.
        """

        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Log in required'}, status=403)
        contact = Contact.objects.filter(
            user_id=request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):

        """
        Проверка авторизации.
        """

        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Log in required'}, status=403)

        if {'city', 'street', 'phone'}.issubset(request.data):
            request.data._mutable = True
            request.data.update({'user': request.user.id})
            serializer = ContactSerializer(data=request.data)

            if serializer.is_valid():
                serializer.save()
                return Response({'Status': True}, status=201)
            else:
                Response({'Status': False,
                          'Errors': serializer.errors})

        return Response({'Status': False,
                         'Errors': 'Отсутствуют обязательные аргументы'}, status=401)

    def put(self, request, *args, **kwargs):

        """
        Проверка авторизации.
        """

        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Log in required'}, status=403)

        if 'id' in request.data:
            if request.data['id'].isdigit():
                contact = Contact.objects.filter(id=request.data['id'], user_id=request.user.id).first()
                print(contact)
                if contact:
                    serializer = ContactSerializer(contact, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return Response({'Status': True})
                    else:
                        Response({'Status': False,
                                  'Errors': serializer.errors})

        return Response({'Status': False,
                         'Errors': 'Отсутствуют обязательные аргументы'}, status=400)

    def delete(self, request, *args, **kwargs):

        """
        Проверка авторизации.
        """

        if not request.user.is_authenticated:
            return Response({'Status': False,
                             'Error': 'Log in required'},
                            status=403)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            query = Q()
            objects_deleted = False
            for contact_id in items_list:
                if contact_id.isdigit():
                    query = query | Q(user_id=request.user.id, id=contact_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = Contact.objects.filter(query).delete()[0]
                return Response({'Status': True,
                                 'Объектов удалено': deleted_count},
                                status=200)
        return Response({'Status': False,
                         'Errors': 'Отсутствуют обязательные аргументы'},
                        status=400)


class OrderView(APIView):
    """ Класс для получения и размещения заказов пользователями. """

    throttle_scope = 'user'

    def get(self, request, *args, **kwargs):
        """
        Метод проверяет авторизацию,
        после чего выдает информацию о заказе.
        """

        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)
        order = Order.objects.filter(
            user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """
        Метод проверяет авторизацию,
        после чего размещает информацию о заказе.
        """

        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Log in required'},
                                status=403)

        if {'id', 'contact'}.issubset(request.data):
            if request.data['id'].isdigit():
                try:
                    is_updated = Order.objects.filter(
                        user_id=request.user.id, id=request.data['id']).update(
                        contact_id=request.data['contact'],
                        state='new')
                except IntegrityError as error:
                    print(error)
                    return JsonResponse({'Status': False,
                                         'Errors': 'Неправильно указаны аргументы'})
                else:
                    if is_updated:
                        # Отправка письма при изменении статуса заказа.
                        user = User.objects.get(id=request.user.id)
                        title = 'Уведомление о смене статуса заказа'
                        message = 'Заказ сформирован.'
                        msg = EmailMultiAlternatives(
                            # title:
                            title,
                            # message:
                            message,
                            # from:
                            settings.EMAIL_HOST_USER,
                            # to:
                            [user.email]
                        )
                        msg.send()

                        return JsonResponse({'Status': True})

        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'})


class PartnerOrders(APIView):
    """ Класс для получения заказов поставщиками. """

    throttle_scope = 'user'

    def get(self, request, *args, **kwargs):
        """
        Метод проверяет авторизацию и тип пользователя (для работы требуется тип 'shop'),
        после чего получает информацию о заказе.
        """
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Log in required'},
                                status=403)

        if request.user.type != 'shop':
            return JsonResponse({'Status': False,
                                 'Error': 'Только для магазинов'},
                                status=403)

        order = Order.objects.filter(
            ordered_items__product_info__shop__user_id=request.user.id).exclude(state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').select_related('contact').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)


class BasketView(APIView):
    """ Класс для работы с корзиной пользователя. """

    throttle_scope = 'user'

    def get(self, request, *args, **kwargs):
        """
        Метод проверяет авторизацию пользователя,
        после чего возвращает информацию о товарах в корзине.
        """

        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=403)

        basket = Order.objects.filter(
            user_id=request.user.id, state='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        """
        Метод проверяет авторизацию пользователя,
        после чего создает для него корзину и добавляет в неё информацию о товарах.
        """

        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = json.loads(items_sting)
            except ValueError:
                JsonResponse({'Status': False,
                              'Errors': 'Неверный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_created = 0
                for order_item in items_dict:
                    order_item.update({'order': basket.id})
                    serializer = OrderItemSerializer(data=order_item)
                    if serializer.is_valid():
                        try:
                            serializer.save()
                        except IntegrityError as error:
                            return JsonResponse({'Status': False,
                                                 'Errors': str(error)})
                        else:
                            objects_created += 1

                    else:

                        JsonResponse({'Status': False,
                                      'Errors': serializer.errors})

                return JsonResponse({'Status': True,
                                     'Создано объектов': objects_created})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'})

    def put(self, request, *args, **kwargs):
        """
        Метод проверяет авторизацию пользователя,
        после чего обновляет информацию о товарах в корзине.
        """

        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = json.loads(items_sting)
            except ValueError:
                JsonResponse({'Status': False,
                              'Errors': 'Неверный формат запроса'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_updated = 0
                for order_item in items_dict:
                    if type(order_item['id']) == int and type(order_item['quantity']) == int:
                        objects_updated += OrderItem.objects.filter(order_id=basket.id, id=order_item['id']).update(
                            quantity=order_item['quantity'])

                return JsonResponse({'Status': True,
                                     'Обновлено объектов': objects_updated})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'})

    def delete(self, request, *args, **kwargs):
        """
        Метод проверяет авторизацию пользователя,
        после чего удаляет информацию о товаре (товарах) в корзине.
        """

        if not request.user.is_authenticated:
            return JsonResponse({'Status': False,
                                 'Error': 'Log in required'}, status=403)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            query = Q()
            objects_deleted = False
            for order_item_id in items_list:
                if order_item_id.isdigit():
                    query = query | Q(order_id=basket.id, id=order_item_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = OrderItem.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True,
                                     'Удалено объектов': deleted_count})
        return JsonResponse({'Status': False,
                             'Errors': 'Не указаны все необходимые аргументы'})


class CategoryView(ListAPIView):
    """Класс для просмотра категорий"""

    queryset = Category.objects.filter(shops__state=True)
    serializer_class = CategorySerializer


class ShopView(ListAPIView):
    """Класс для просмотра списка магазинов"""

    queryset = Shop.objects.filter(state=True)
    serializer_class = ShopSerializer


class ProductInfoView(ModelViewSet):
    """Класс для поиска товаров"""

    throttle_classes = [UserRateThrottle, AnonRateThrottle]

    queryset = ProductInfo.objects.filter(shop__state=True).select_related(
        'shop', 'product__category'
    ).prefetch_related('product_parameters__parameter').distinct()

    serializer_class = ProductInfoSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ('product__name', 'shop_id', 'product__category_id')


class SellerUpdateCatalog(APIView):
    """Класс для обновления каталога от продавца"""

    permission_classes = [IsAuthenticated, IsShopUser]

    def post(self, request, *args, **kwargs):
        url = request.data.get('url')

        if url:
            validate_url = URLValidator()

            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({'Status': False, 'Error': str(e)})
            else:
                stream = requests.get(url).content
                data = load_yaml(stream, Loader=Loader)

                # Если у пользователя нет магазина - создать
                if not Shop.objects.filter(user_id=request.user.id).exists():
                    shop = Shop.objects.create(name=data['shop'], user_id=request.user.id)
                # Иначе получить магазин
                else:
                    shop = Shop.objects.get(user_id=request.user.id)

                # И обновить название
                shop.name = data['shop']
                shop.save()

                for category in data['categories']:
                    if not Category.objects.filter(id=category['id']).exists():
                        category_object = Category.objects.create(id=category['id'], name=category['name'])
                    else:
                        category_object = Category.objects.get(id=category['id'])

                    category_object.shops.add(shop.id)
                    category_object.save()

                ProductInfo.objects.filter(shop_id=shop.id).delete()

                for item in data['goods']:
                    product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])

                    product_info = ProductInfo.objects.create(product_id=product.id,
                                                              external_id=item['id'],
                                                              model=item['model'],
                                                              price=item['price'],
                                                              price_rrc=item['price_rrc'],
                                                              quantity=item['quantity'],
                                                              shop_id=shop.id)

                    for name, value in item['parameters'].items():
                        parameter_object, _ = Parameter.objects.get_or_create(name=name)
                        ProductParameter.objects.create(product_info_id=product_info.id,
                                                        parameter_id=parameter_object.id,
                                                        value=value)

                return JsonResponse({'Status': True})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})


class SellerState(APIView):
    """Класс для работы со статусом продавца"""

    permission_classes = [IsAuthenticated, IsShopUser]

    # Получить текущий статус
    def get(self, request, *args, **kwargs):
        shop = request.user.shop
        serializer = ShopSerializer(shop)
        return Response(serializer.data)

    # Изменить текущий статус
    def post(self, request, *args, **kwargs):
        state = request.data.get('state')

        if state:
            try:
                Shop.objects.filter(user_id=request.user.id).update(state=strtobool(state))
                return JsonResponse({'Status': True})
            except ValueError as error:
                return JsonResponse({'Status': False, 'Errors': str(error)})

        return JsonResponse({'Status': False, 'Errors': 'Не указаны все необходимые аргументы'})
