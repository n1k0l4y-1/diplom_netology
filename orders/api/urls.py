from django.urls import path, include
from django_rest_passwordreset.views import reset_password_request_token, reset_password_confirm
from rest_framework.routers import DefaultRouter

from .views import RegisterAccount, LoginAccount, AccountDetails, ContactView, ConfirmAccount, PartnerOrders, OrderView, \
    BasketView, ProductInfoView, CategoryView, ShopView, SellerUpdateCatalog, SellerState

app_name = 'api'
router = DefaultRouter()
router.register(r'products', ProductInfoView, basename='products')

urlpatterns = [
    path('user/register', RegisterAccount.as_view(), name='user-register'),
    path('user/register/confirm', ConfirmAccount.as_view(), name='user-register-confirm'),
    path('user/details', AccountDetails.as_view(), name='user-details'),
    path('user/contact', ContactView.as_view(), name='user-contact'),
    path('user/login', LoginAccount.as_view(), name='user-login'),
    path('user/password_reset', reset_password_request_token, name='password-reset'),
    path('user/password_reset/confirm', reset_password_confirm, name='password-reset-confirm'),
    path('partner/orders', PartnerOrders.as_view(), name='partner-orders'),
    path('order', OrderView.as_view(), name='order'),
    path('basket', BasketView.as_view(), name='basket'),
    path('categories', CategoryView.as_view(), name='categories'),
    path('shops', ShopView.as_view(), name='shops'),
    path('seller/update', SellerUpdateCatalog.as_view(), name='partner-update'),
    path('seller/state', SellerState.as_view(), name='partner-state'),
    path('', include(router.urls)),
]
