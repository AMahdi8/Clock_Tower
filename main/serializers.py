from datetime import datetime
from jdatetime import datetime as Jdatetime

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import TokenCreateSerializer as BaseTokenCreateSerializer
from djoser.serializers import TokenSerializer as BaseTokenSerializer
from django_jalali.serializers import serializerfield
from .models import *
from .utility import get_available_discounts, get_available_room, get_available_rooms
import pytz

User = get_user_model()


class CartItemSerializers(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ['id', 'room_type', 'quantity', 'total_price']

    total_price = serializers.SerializerMethodField(
        method_name='calculat_total_price',
    )

    def calculat_total_price(self, item: CartItem):
        return (item.room_type.price_per_night * item.quantity) * (item.cart.end_booking - item.cart.start_booking).days


class AddItemsToCartSerializers(serializers.ModelSerializer):
    price = serializers.IntegerField(read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'room_type', 'quantity', 'price']

    def create(self, validated_data):
        cart_id = self.context['cart_id']
        room_type = self.validated_data['room_type']
        quantity = self.validated_data['quantity']

        cart = Cart.objects.get(id=cart_id)

        room_type_available_number = get_available_rooms(
            cart.start_booking, cart.end_booking)[room_type.room_type]

        try:
            cart_item = CartItem.objects.get(
                cart_id=cart_id, room_type=room_type)
            if quantity < 1:
                cart_item.delete()
                return cart_item
            if quantity > room_type_available_number:
                raise serializers.ValidationError(
                    'The rooms you want is greater than what we have.'
                )
            cart_item.quantity = quantity
            cart_item.save()
            self.instance = cart_item
        except CartItem.DoesNotExist:
            cart_item = CartItem.objects.create(
                cart_id=cart_id, **validated_data)
            self.instance = cart_item

        return self.instance


class CartSerializers(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    items = CartItemSerializers(many=True, read_only=True)
    total_price = serializers.SerializerMethodField(
        method_name='calculat_total_price'
    )
    final_price = serializers.IntegerField(
        source='get_final_price', read_only=True)
    total_capacity = serializers.IntegerField(
        source='get_total_capacity', read_only=True)
    start_booking = serializerfield.JDateField()
    end_booking = serializerfield.JDateField()

    class Meta:
        model = Cart
        fields = ['id', 'items', 'adults', 'kids', 'start_booking',
                  'end_booking', 'total_price', 'final_price', 'total_capacity']

    def validate_adults(self, value):
        if not value:
            raise serializers.ValidationError(
                'تعداد بزرگسال باید بزرگتر از صفر باشد.')
        return value

    def validate(self, data):
        if data['start_booking'] >= data['end_booking']:
            raise serializers.ValidationError({
                "start_booking, end_booking": "تاریخ شروع نمیتواند دیرتر از تاریخ پایان باشد."
            })
        elif data['start_booking'] < datetime.now().date():
            raise serializers.ValidationError({
                "start_booking": "تاریخ شروع نمیتواند دیرتر از تاریخ امروز باشد."
            })
        return data

    def calculat_total_price(self, cart: Cart):
        return sum([item.room_type.price_per_night *
                    item.quantity for item in cart.items.all()]) * \
            (cart.end_booking - cart.start_booking).days


class SimpleCartItemSerializers(serializers.ModelSerializer):
    class Meta:
        model = CartItem
        fields = ['quantity']


class UpdateCartSerializers(serializers.ModelSerializer):
    items = SimpleCartItemSerializers(many=True)

    class Meta:
        model = Cart
        fields = ['adults', 'kids', 'items']

    def validate_adults(self, value):
        if not value:
            raise serializers.ValidationError(
                'تعداد بزرگسال باید بزرگتر از صفر باشد.')
        return value

    def update(self, instance, validated_data):
        with transaction.atomic():
            cart = Cart.objects.prefetch_related('items').get(pk=str(instance))
            cart_items = CartItem.objects.filter(cart=cart)
            start = cart.start_booking
            end = cart.end_booking
            cart.adults = validated_data['adults']
            cart.kids = validated_data['kids']
            total_persons = cart.kids + cart.adults

            if cart.total_capacity < total_persons:
                raise serializers.ValidationError(
                    "The total number of people exceeds the combined capacity of the selected rooms."
                )

            rooms = get_available_rooms(start, end)
            for i in range(len(cart_items)):
                if not validated_data['items'][i]['quantity']:
                    cart_items[i].delete()
                    continue
                if rooms[cart_items[i].room_type.room_type] < validated_data['items'][i]['quantity']:
                    raise serializers.ValidationError(
                        "The rooms you want is greater than what we have.")
                cart_items[i].quantity = validated_data['items'][i]['quantity']
                cart_items[i].save()
            cart.save()

            return instance


class GetCustomUserSerializersForOrder(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['phone_number', 'id_number', 'first_name', 'last_name']


class CustomerDiscountSerializers(serializers.ModelSerializer):
    class Meta:
        model = CustomerDiscount
        fields = ['code', 'percent']


class OrderItemSerializers(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['room_type', 'quantity']


class OrderSerializers(serializers.ModelSerializer):
    items = OrderItemSerializers(many=True)
    customer = GetCustomUserSerializersForOrder(many=False, read_only=True)
    start_booking = serializerfield.JDateField()
    end_booking = serializerfield.JDateField()
    discount = CustomerDiscountSerializers(many=False)

    class Meta:
        model = Order
        fields = ['id', 'customer', 'payment_status', 'adults', 'kids', 'start_booking',
                  'end_booking', 'final_price', 'items', 'extra_explanation', 'discount']


class CreateOrderSerializers(serializers.Serializer):
    cart_id = serializers.UUIDField()

    def validate_cart_id(self, value):
        if not Cart.objects.filter(id=value).exists():
            raise serializers.ValidationError('No cart id with this id')
        if not CartItem.objects.filter(cart=value).count():
            raise serializers.ValidationError('Cart is empty')
        return value

    def validate(self, data):
        cart_id = data['cart_id']
        cart = Cart.objects.get(id=cart_id)

        total_people = cart.adults + cart.kids
        total_capacity = sum(
            item.quantity * (item.room_type.capacity+1) for item in cart.items.all())

        if total_people > total_capacity:
            raise serializers.ValidationError(
                "The total number of people exceeds the combined capacity of the selected rooms.")
        return data

    def save(self, **kwargs):
        cart_id = self.validated_data['cart_id']
        cart = Cart.objects.get(id=cart_id)
        user = CustomUser.objects.get(id=self.context['user_id'])

        cart_items = CartItem.objects.select_related(
            'room_type').filter(cart_id=cart_id)

        total_persons = cart.adults + cart.kids

        if cart.total_capacity < total_persons:
            raise serializers.ValidationError(
                "The total number of people exceeds the combined capacity of the selected rooms."
            )

        rooms = get_available_rooms(cart.start_booking, cart.end_booking)
        for i in range(len(cart_items)):
            if rooms[cart_items[i].room_type.room_type] < cart_items[i].quantity:
                raise serializers.ValidationError(
                    "The rooms you want is greater than what we have.")

        with transaction.atomic():
            order = Order.objects.create(
                customer=user,
                adults=cart.adults,
                kids=cart.kids,
                start_booking=cart.start_booking,
                end_booking=cart.end_booking,
                final_price=cart.final_price,
                total_capacity=cart.total_capacity
            )

            order_items = [
                OrderItem(
                    order=order,
                    room_type=item.room_type,
                    quantity=item.quantity,
                    price=item.price
                )
                for item in cart_items
            ]

            OrderItem.objects.bulk_create(order_items)

            Cart.objects.filter(pk=cart_id).delete()

        return order

# class UpdateOrderSerializers(serializers.Serializer):
#     discount_code = serializers.CharField()
#     extra_explanation = serializers.CharField()

#     def validate_discount_code(self, code):
#         discount = CustomerDiscount.objects.filter(code=code)
#         if discount


class UpdateOrderSerializers(serializers.ModelSerializer):
    items = OrderItemSerializers(many=True, read_only=True)
    customer = GetCustomUserSerializersForOrder(many=False, read_only=True)
    start_booking = serializerfield.JDateField()
    end_booking = serializerfield.JDateField()

    class Meta:
        model = Order
        fields = ['id', 'customer', 'start_booking', 'end_booking',
                  'adults', 'kids', 'final_price', 'items', 'extra_explanation', 'discount_code']
        extra_kwargs = {
            'start_booking': {'read_only': True},
            'end_booking': {'read_only': True},
            'adults': {'read_only': True},
            'kids': {'read_only': True}
        }

    def validate_discount_code(self, code):
        if not code:
            code = ''
            return code

        discount = CustomerDiscount.objects.filter(code=code).first()

        if not discount:
            raise serializers.ValidationError(
                'Please Enter a valid code and try again.')

        if CustomerDiscountUsage.objects.filter(
            discount=discount,
            customer=self.context['customer']
        ).exists():
            raise serializers.ValidationError(
                'You already used this discount code.')

        if not discount.quantity:
            raise serializers.ValidationError(
                'Discount code is run out of number.')

        if discount.start > Jdatetime.now() or discount.end < Jdatetime.now():
            raise serializers.ValidationError(
                'Discount expired.'
            )

        return code

    def update(self, instance: Order, validated_data):
        order = instance

        if not validated_data['discount_code']:
            order.extra_explanation = validated_data['extra_explanation']
            order.save()
            instance = order
            return instance

        if order.discount:
            raise serializers.ValidationError(
                'You can only use one discount'
            )

        discount = CustomerDiscount.objects.get(
            code=validated_data['discount_code'])

        discount_usage = CustomerDiscountUsage.objects.create(
            discount=discount, customer=self.context['customer'])

        discount.quantity -= 1
        discount.save()

        order.final_price = order.final_price - \
            (discount.percent * order.final_price // 100)

        order.discount_code = validated_data['discount_code']
        order.discount = discount
        order.discount_usage = discount_usage
        order.extra_explanation = validated_data['extra_explanation']

        order.save()
        instance = order

        return instance


class ReservedOrderSerializers(serializers.ModelSerializer):
    items = OrderItemSerializers(many=True, read_only=True)
    customer = GetCustomUserSerializersForOrder(many=False, read_only=True)
    payment_status = serializers.CharField(max_length=1, required=True)

    class Meta:
        model = Order
        fields = ['id', 'customer', 'payment_status', 'items']

    def validate_payment_status(self, status):
        if status not in ['C', 'F', 'P']:
            raise serializers.ValidationError('Invalid payment status.')
        return status

    def update(self, instance, validated_data):
        with transaction.atomic():

            last_payment_status = instance.payment_status

            if last_payment_status == "C":
                raise serializers.ValidationError(
                    "this order already completed.")

            instance.payment_status = validated_data.get(
                'payment_status', instance.payment_status)
            instance.save()

            if instance.payment_status == 'C':

                start = instance.start_booking
                end = instance.end_booking
                for item in instance.items.all():
                    for _ in range(item.quantity):
                        room_availability = get_available_room(start, end)
                        available_rooms = room_availability.get(
                            item.room_type.id, [])

                        if not available_rooms:
                            raise serializers.ValidationError(
                                'No available rooms for the selected room type.')

                        room = available_rooms[0]
                        Reservation.objects.create(
                            order=instance,
                            room=room,
                            check_in=start,
                            check_out=end
                        )

            return instance


class SendOtpSerializers(serializers.Serializer):
    phone_number = serializers.CharField(max_length=11)

    def validate_phone_number(self, value):
        if not value.isnumeric() or len(value) != 10 or int(value[0]) != 9:
            raise serializers.ValidationError(
                "Please enter a valid phone number.")
        return value


class VerifyOtpSerializers(serializers.Serializer):
    phone_number = serializers.CharField(max_length=10)
    otp_code = serializers.CharField(max_length=6)

    def validate_phone_number(self, value):
        if not CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(
                "User with this phone number does not exist.")
        return value


class CustomUserSerializers(serializers.ModelSerializer):
    phone_number = serializers.CharField(max_length=10, read_only=True)
    orders = OrderSerializers(many=True, read_only=True)
    birth_date = serializerfield.JDateField()

    class Meta:
        model = CustomUser
        fields = ['id', 'phone_number', 'id_number', 'email',
                  'birth_date', 'first_name', 'last_name', 'orders']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        orders = Order.objects.filter(customer=instance)
        representation['orders'] = OrderSerializers(orders, many=True).data
        return representation


class UpdateCustomUserSerializers(serializers.ModelSerializer):
    phone_number = serializers.CharField(max_length=10, read_only=True)
    birth_date = serializerfield.JDateField()

    class Meta:
        model = CustomUser
        fields = ['phone_number', 'id_number', 'email',
                  'birth_date', 'first_name', 'last_name']


class CreateCustomUserSerializers(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['phone_number']


class RoomTypeImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = RoomTypeImage
        fields = ['image_url']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if request is not None:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class RoomDiscountSerializers(serializers.ModelSerializer):
    start = serializerfield.JDateTimeField()
    end = serializerfield.JDateTimeField()

    class Meta:
        model = RoomDiscount
        fields = ['title', 'percent', 'end', 'start']


class RoomTypeSerializers(serializers.ModelSerializer):
    images = RoomTypeImageSerializer(many=True, read_only=True)

    class Meta:
        model = RoomType
        fields = ['room_type', 'capacity', 'extra',
                  'price_per_night', 'description', 'images']


class FilterRoomTypeSerializers(serializers.ModelSerializer):
    images = RoomTypeImageSerializer(many=True, read_only=True)
    available_rooms = serializers.SerializerMethodField(
        method_name='get_rooms'
    )
    available_discounts = serializers.SerializerMethodField(
        method_name='get_discounts'
    )

    class Meta:
        model = RoomType
        fields = ['room_type', 'capacity', 'extra', 'available_discounts',
                  'price_per_night', 'description', 'images', 'available_rooms']

    def get_rooms(self, obj):
        rooms = self.context['available_rooms']
        return rooms[obj.room_type]

    def get_discounts(self, obj):
        discounts = self.context['available_discounts']
        result = []
        for discount in discounts[obj.room_type]:
            result.append(discount)

        return result


class NotificationSerializers(serializers.ModelSerializer):
    image = serializers.ImageField()
    start_date = serializerfield.JDateTimeField()
    end_date = serializerfield.JDateTimeField()

    class Meta:
        model = Notification
        fields = ['id', 'title', 'description', 'image',
                  'start_date', 'end_date']
