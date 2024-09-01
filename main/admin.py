from django.contrib import admin
from django.db.models.query import QuerySet
from django.db.models.aggregates import Count
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from typing import Any

from . import models


@admin.register(models.RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ['room_type',  'capacity', 'number_of_rooms',
                    'price_per_night', 'image']  # 'number_of_availabe_rooms'
    list_editable = ['price_per_night']
    list_per_page = 10

    @admin.display(ordering='number_of_rooms')
    def number_of_rooms(self, room_type):
        url = (
            reverse('admin:main_room_changelist')
            + '?'
            + urlencode({'room_type__id': str(room_type.id)}
                        ))
        return format_html('<a href="{}">{} Rooms</a>', url, room_type.number_of_rooms)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Any]:
        return super().get_queryset(request).annotate(
            number_of_rooms=Count('rooms')
        )

    def image(self, room_type):
        return room_type.images


@admin.register(models.RoomTypeImage)
class RoomTypeImageAdmin(admin.ModelAdmin):
    list_display = ['room_type', 'image']
    list_editable = ['image']
    list_per_page = 10


@admin.register(models.Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['room_number', 'room_type',
                    'room_capacity', 'price_per_night']
    list_per_page = 10
    list_select_related = ['room_type']

    def room_capacity(self, room):
        return room.room_type.capacity

    def price_per_night(self, room):
        return room.room_type.price_per_night


@admin.register(models.CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'birth_date']
    list_per_page = 10


@admin.register(models.CustomerDiscount)
class CustomerDiscountAdmin(admin.ModelAdmin):
    list_display = ['code', 'quantity', 'percent', 'start', 'end']
    list_per_page = 10


@admin.register(models.CustomerDiscountUsage)
class CustomerDiscountUsageAdmin(admin.ModelAdmin):
    list_display = ['customer', 'discount', 'used_at']
    list_select_related = ['customer', 'discount']
    list_per_page = 10
    list_select_related = ['customer', 'discount']


def customer(self, usage):
    return usage.customer.phone_number


def discount(self, usage):
    return usage.discount.percent


@admin.register(models.Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'adults', 'kids',
                    'start_booking', 'end_booking', 'number_of_items']
    list_per_page = 10

    @admin.display(ordering='number_of_items')
    def number_of_items(self, cart):
        url = (
            reverse('admin:main_cartitem_changelist')
            + '?'
            + urlencode({'cart__id': str(cart.id)}
                        ))
        return format_html('<a href="{}">{} Carts</a>', url, cart.number_of_items)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            number_of_items=Count('items')

        )


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['placed_at', 'payment_status', 'customer', 'adults',
                    'kids', 'start_booking', 'end_booking', 'discount', 'number_of_items']
    list_per_page = 10
    list_select_related = ['customer', 'discount']

    @admin.display(ordering='number_of_items')
    def number_of_items(self, order):
        url = (
            reverse('admin:main_orderitem_changelist')
            + '?'
            + urlencode({
                'order__id': str(order.id)
            }))
        return format_html('<a href="{}">{} Orders</a>', url, order.number_of_items)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            number_of_items=Count('items')
        )

    def customer(self, order):
        return order.custoemr.phone_numebr

    def discount(self, order):
        return order.discount.percent


@admin.register(models.Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['order', 'room']
    list_editable = ['room']
    list_per_page = 10


@admin.register(models.OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['room_type', 'quantity']
    list_editable = ['quantity']
    list_display_links = ['room_type']
    list_per_page = 10


@admin.register(models.CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['room_type', 'quantity']
    list_editable = ['quantity']
    list_display_links = ['room_type']
    list_per_page = 10


@admin.register(models.RoomDiscount)
class RoomDiscountAdmin(admin.ModelAdmin):
    list_display = ['room_type', 'title', 'percent', 'start', 'end']
    list_per_page = 10
