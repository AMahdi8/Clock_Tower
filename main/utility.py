import pyotp
from datetime import datetime, timedelta
from django.db.models import Q

from .models import Reservation, Room, RoomDiscount, RoomType
from sms_ir import SmsIr

def get_available_rooms(start_date, end_date):
    reserved_rooms = Reservation.objects.filter(
        Q(check_in__lt=end_date) & Q(check_out__gt=start_date)
    ).values_list('room_id', flat=True)

    all_room_types = RoomType.objects.all()

    available_rooms_dict = {}

    for room in all_room_types:
        available_rooms_count = Room.objects.filter(
            room_type=room)
        room_count = available_rooms_count.count()
        for i in available_rooms_count:
            if i.room_number in reserved_rooms:
                room_count -= 1
        available_rooms_dict[room.room_type] = room_count

    return available_rooms_dict


def get_available_discounts(now):
    available_discounts = RoomDiscount.objects.filter(
        Q(start__lte=now) & Q(end__gte=now)
    )

    all_room_types = RoomType.objects.all()

    available_discount_dict = {}

    for room in all_room_types:
        discounts = []
        for i in available_discounts:
            if i.room_type == room:
                discounts.append(i)
        available_discount_dict[room.room_type] = list(
            [discount.title, discount.percent] for discount in discounts)

    return available_discount_dict


def get_available_room(start_date, end_date):
    reserved_room_ids = Reservation.objects.filter(
        Q(check_in__lt=end_date) & Q(check_out__gt=start_date)
    ).values_list('room_id', flat=True)

    room_availability = {}

    all_room_types = RoomType.objects.all()

    for room_type in all_room_types:
        available_rooms = Room.objects.filter(
            room_type=room_type
        ).exclude(room_number__in=reserved_room_ids)

        room_availability[room_type.id] = available_rooms

    return room_availability


def send_otp(request):
    totp = pyotp.TOTP(pyotp.random_base32(), interval=120)
    otp = totp.now()
    request.sessions['otp_secret_key'] = totp.secre

    valid_date = datetime.now() + timedelta(minuts=2)
    request.session['otp_valid_date'] = str(valid_date)

def send_sms(request, otp_code, phone_number):
        sms_ir = SmsIr(
            'rSDQ71JQonDYWwIXsZThrQBXEcjGYY64Oz4HDix8ctgyyWfuSweFQ6vZxgB6olAK',
            30007487125280
        )
        sms_ir.send_verify_code(
            number=f"+98{phone_number}",
            template_id=100000,
            parameters=[
                {
                    "name": "code",
                    "value": otp_code,
                },
            ],
        )