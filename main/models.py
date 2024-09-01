from datetime import datetime
import os
from typing import Iterable
from uuid import uuid4
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.conf import settings
from django_jalali.db import models as Jmodels


class RoomType(models.Model):
    ROOM_TYPE_CHOICES = (
        ('double', 'دبل'),
        ('royal_double', 'رویال دبل'),
        ('twin', 'تویین'),
        ('royal_twin', 'رویال تویین'),
        ('one_bed', 'تک خوابه'),
        ('two_bed', 'دو خوابه'),
        ('three_bed', 'سه تخته'),
        ('connect', 'کانکت'),
    )

    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES)
    quantity = models.PositiveSmallIntegerField()
    capacity = models.PositiveSmallIntegerField()
    extra = models.BooleanField(default=True)
    price_per_night = models.IntegerField()
    description = models.TextField()

    def __str__(self) -> str:
        return f'{self.room_type}'

    class Meta:
        ordering = ['room_type', 'price_per_night']


class Room(models.Model):
    room_number = models.IntegerField(primary_key=True)
    room_type = models.ForeignKey(
        RoomType, on_delete=models.CASCADE, related_name='rooms')

    def __str__(self) -> str:
        return f'{self.room_number}'

    class Meta:
        ordering = ['room_number']


class RoomTypeImage(models.Model):
    room_type = models.ForeignKey(
        'RoomType', on_delete=models.CASCADE, related_name='images', default=None)
    image = models.ImageField(upload_to='roomtype/')


class RoomDiscount(models.Model):
    room_type = models.ForeignKey(
        RoomType, on_delete=models.CASCADE, related_name='room_discounts')
    title = models.CharField(max_length=255)
    percent = models.PositiveSmallIntegerField()
    start = Jmodels.jDateTimeField()
    end = Jmodels.jDateTimeField()


class CustomUserManager(BaseUserManager):

    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('The Phone Number must be set')
        user = self.model(phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone_number, password, **extra_fields)


class CustomUser(AbstractUser):
    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []
    username = None

    phone_number = models.CharField(
        max_length=10, unique=True)
    id_number = models.CharField(
        max_length=10, null=True, blank=True)
    birth_date = Jmodels.jDateField(null=True, blank=True)

    objects = CustomUserManager()

    def __str__(self) -> str:
        return f'{self.phone_number}'


class OTP(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    otp_code = models.CharField(max_length=6)
    created_at = Jmodels.jDateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'otp_code')


class CustomerDiscount(models.Model):
    code = models.CharField(max_length=30, unique=True)
    quantity = models.IntegerField(default=1000000)
    percent = models.PositiveSmallIntegerField()
    start = Jmodels.jDateTimeField()
    end = Jmodels.jDateTimeField()

    def __str__(self) -> str:
        return f'{self.code}-{self.percent}'


class CustomerDiscountUsage(models.Model):
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    discount = models.ForeignKey(CustomerDiscount, on_delete=models.CASCADE)
    used_at = Jmodels.jDateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('customer', 'discount')

    def __str__(self) -> str:
        return f'{self.customer}'


class Cart(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4)
    created_at = Jmodels.jDateTimeField(auto_now_add=True)
    adults = models.PositiveSmallIntegerField()
    kids = models.PositiveSmallIntegerField(default=0)
    final_price = models.IntegerField(default=0)
    total_capacity = models.PositiveSmallIntegerField(default=0)
    start_booking = Jmodels.jDateField()
    end_booking = Jmodels.jDateField()

    def __str__(self) -> str:
        return f'{self.id}'

    def get_total_capacity(self):
        items = self.items.all()
        self.total_capacity = 0
        for item in items:
            self.total_capacity += (item.room_type.capacity+1) * item.quantity

        self.save()
        return self.total_capacity

    def get_final_price(self):
        items = self.items.all()
        from .utility import get_available_discounts
        discounts = get_available_discounts(datetime.now())
        self.final_price = 0
        for item in items:
            total_price = (item.price * item.quantity) * \
                (self.end_booking - self.start_booking).days
            for discount in discounts[item.room_type.room_type]:
                percent = discount[1]
                total_price = total_price - (total_price * percent//100)

            self.final_price += total_price

        self.save()
        return self.final_price


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name='items')
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField()
    price = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return f'{self.room_type.room_type}-{self.quantity}'

    def save(self, *args, **kwrgs):
        self.price = self.room_type.price_per_night
        return super().save()


class Order(models.Model):
    PAYMENT_STATUS_PENDING = 'P'
    PAYMENT_STATUS_COMPLETE = 'C'
    PAYMENT_STATUS_FAILED = 'F'
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_STATUS_PENDING, 'در انتظار'),
        (PAYMENT_STATUS_COMPLETE, 'موفق'),
        (PAYMENT_STATUS_FAILED, 'ناموفق')
    ]

    placed_at = Jmodels.jDateTimeField(auto_now_add=True)
    payment_status = models.CharField(
        max_length=1, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_PENDING)
    customer = models.ForeignKey(CustomUser, on_delete=models.PROTECT)
    final_price = models.PositiveIntegerField()
    total_capacity = models.PositiveSmallIntegerField()
    adults = models.PositiveSmallIntegerField()
    kids = models.PositiveSmallIntegerField()
    start_booking = Jmodels.jDateField()
    end_booking = Jmodels.jDateField()
    extra_explanation = models.TextField(blank=True)
    discount_code = models.CharField(max_length=255, blank=True, null=True)
    discount = models.ForeignKey(
        CustomerDiscount, on_delete=models.SET_NULL, related_name='orders', blank=True, null=True)
    discount_usage = models.ForeignKey(
        CustomerDiscountUsage, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self) -> str:
        return f'{self.customer}-{self.placed_at}'


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='items')
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField()
    price = models.PositiveBigIntegerField()

    def __str__(self) -> str:
        return f'{self.room_type.room_type}-{self.quantity}'


class Reservation(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='reservations')
    room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name='reservations')
    check_in = Jmodels.jDateField()
    check_out = Jmodels.jDateField()

    def __str__(self) -> str:
        return f'Reservation for Order {self.order.id} - Room {self.room.room_number}'


class Notification(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    image = models.ImageField(upload_to='notif/')
    start_date = Jmodels.jDateTimeField()
    end_date = Jmodels.jDateTimeField()


# find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
# find . -path "*/migrations/*.pyc"  -delete
