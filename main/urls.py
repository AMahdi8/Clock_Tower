from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from .views import *

main_router = DefaultRouter()
main_router.register('auth', CustomUserViewSet, basename='auth')
main_router.register('rooms', RoomTypeViewSet, basename='rooms')
main_router.register('carts', CartViewSet, basename='carts')
main_router.register('orders', OrderViewSet, basename='orders')
main_router.register('notifications', NotificationViewSet,
                     basename='notifications')

cart_router = routers.NestedDefaultRouter(main_router, 'carts', lookup='cart')
cart_router.register('items', CartItemViewSet, basename='cart_item')

urlpatterns = [
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.jwt')),
    path('orders/<int:pk>/reserved/',
         OrderViewSet.as_view({'patch': 'reserved'}), name='order-reserved'),
    path('', home, name='home'),
] + main_router.urls + cart_router.urls


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
