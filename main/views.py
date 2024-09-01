from datetime import datetime, timedelta
from jdatetime import datetime as Jdatetime
import random


from django.utils import timezone
from django.shortcuts import get_list_or_404, render, get_object_or_404
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.mixins import *
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework import status
from rest_framework.decorators import action, api_view
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView


from .premissions import IsAdminOrReadOnly
from .serializers import *
from .models import *
from .utility import get_available_rooms, send_otp, get_available_discounts, send_sms


class RoomTypeViewSet(ModelViewSet):
    queryset = RoomType.objects.prefetch_related('images').all()
    serializer_class = RoomTypeSerializers
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['GET'], permission_classes=[AllowAny])
    def available_rooms(self, request):
        now = datetime.now()
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        if not start_date_str or not end_date_str:
            return Response({'error': 'Start date and end date are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            start_date = Jdatetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = Jdatetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format, User YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)

        if start_date >= end_date:
            return Response({'error': 'End date must be after start date.'}, status=status.HTTP_400_BAD_REQUEST)
        
        if start_date < Jdatetime.now().date():
            return Response({'error': 'Your reservation must be after today.'}, status=status.HTTP_400_BAD_REQUEST)

        # if end_date > datetime.now().date() + timedelta(days=365):
        #     return Response({'error': 'You can\'t reserve room for next year.'})

        available_rooms = get_available_rooms(start_date, end_date)
        available_discounts = get_available_discounts(now)


        serializers = FilterRoomTypeSerializers(self.queryset, many=True, context={
            'available_rooms': available_rooms,
            'available_discounts': available_discounts})

        return Response(serializers.data, status=status.HTTP_200_OK)


class CartViewSet(CreateModelMixin,
                  RetrieveModelMixin,
                  DestroyModelMixin,
                  UpdateModelMixin,
                  GenericViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    queryset = Cart.objects.prefetch_related('items').all()
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return UpdateCartSerializers
        return CartSerializers


class CartItemViewSet(ModelViewSet):
    # check here again for patching that you delete
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_serializer_context(self):
        return {'cart_id': self.kwargs['cart_pk']}

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AddItemsToCartSerializers
        return CartItemSerializers

    def get_queryset(self):
        return CartItem.objects\
            .filter(cart_id=self.kwargs['cart_pk'])\
            .select_related('room_type')


class CustomUserViewSet(UpdateModelMixin,
                        GenericViewSet):
    queryset = CustomUser.objects.all()

    def get_permissions(self):
        if self.request.method == 'POST':
            return [AllowAny()]
        elif self.request.method == 'PATCH':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CreateCustomUserSerializers
        return CustomUserSerializers

    @action(detail=False, methods=['GET', 'PATCH'], permission_classes=[IsAuthenticated])
    def me(self, request):
        customer = CustomUser.objects.get(
            id=request.user.id
        )
        if request.method == 'GET':
            serializers = CustomUserSerializers(customer)
            return Response(serializers.data)
        elif request.method == 'PATCH':
            serializers = UpdateCustomUserSerializers(customer, request.data)
            serializers.is_valid(raise_exception=True)
            serializers.save()
            return Response(serializers.data)

    @action(detail=False,  methods=['POST'], permission_classes=[AllowAny])
    def send_otp(self, request):
        serializers = SendOtpSerializers(data=request.data)
        serializers.is_valid(raise_exception=True)
        phone_number = serializers.validated_data['phone_number']
        user, create = CustomUser.objects.get_or_create(
            phone_number=phone_number)

        otp_code = str(random.randint(100000, 999999))

        try:
            otp = OTP.objects.get(user=user)

            if otp.created_at > timezone.now() - timedelta(minutes=2):
                x = otp.created_at - timezone.now() + timedelta(minutes=2)
                return Response({'error': f'You should {x.seconds} second for get new code.'}, status=status.HTTP_400_BAD_REQUEST)

            otp.delete()

            otp = OTP.objects.create(user=user, otp_code=otp_code)

        except Exception:
            otp = OTP.objects.create(user=user, otp_code=otp_code)

        otp.save()
        send_sms(request, otp_code, phone_number)
        print(otp_code)  # delete this

        if create:
            return Response({"message": "OTP sent successfully"}, status=status.HTTP_201_CREATED)
        return Response({"message": "OTP sent successfully"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['POST'], permission_classes=[AllowAny])
    def verify_otp(self, request):
        serializers = VerifyOtpSerializers(data=request.data)
        serializers.is_valid(raise_exception=True)
        otp_code = serializers.validated_data['otp_code']
        phone_number = serializers.validated_data['phone_number']
        try:
            user = User.objects.get(phone_number=phone_number)
            otp = OTP.objects.filter(user=user, otp_code=otp_code).first()

            if not otp:
                return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

            if otp.created_at < timezone.now() - timedelta(minutes=2):
                return Response({'error': 'Code has heen expired.'}, status=status.HTTP_400_BAD_REQUEST)

            refresh = RefreshToken.for_user(user)
            otp.delete()
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })

        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_400_BAD_REQUEST)

    # @action(detail=False, methods=["POST"], permission_classes=[IsAuthenticated])
    # def logout(self, request):
    #     customer = CustomUser.objects.get(
    #         id=request.user.id
    #     )
    #     customer.pho


class OrderViewSet(ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.request.method == 'DELETE':
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializers = CreateOrderSerializers(
            data=request.data,
            context={'user_id': self.request.user.id})
        serializers.is_valid(raise_exception=True)
        order = serializers.save()
        serializers = OrderSerializers(order)
        return Response(serializers.data)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({'customer': self.request.user})
        return context

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return UpdateOrderSerializers
        if self.request.method == 'POST':
            return CreateOrderSerializers
        return OrderSerializers

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.select_related('customer').all()

        customer_id = CustomUser.objects.only(
            'id').get(id=user.id)
        return Order.objects.select_related('customer').filter(customer=customer_id)

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def reserved(self, request, pk=None):
        payment_status = self.request.data.get('payment_status')

        try:
            order = Order.objects.get(pk=pk)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if payment_status not in ['C', 'F', 'P']:
            return Response({'error': 'Invalid payment status.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ReservedOrderSerializers(
            order, data={'payment_status': payment_status}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({'message': 'Payment status updated successfully.'}, status=status.HTTP_200_OK)


class NotificationViewSet(ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializers
    permission_classes = [IsAdminUser]


@api_view(['GET'])
def home(request):
    now = datetime.now()
    queryset = Notification.objects.filter(
        Q(start_date__lte=now) & Q(end_date__gte=now)
    )
    user = request.user
    try:
        full_name = CustomUser.objects.get(phone_number=user).get_full_name()
        if full_name:
            user = full_name
    except Exception:
        user = "Dear Guest"

    serializer = NotificationSerializers(queryset, many=True)

    return Response(data={'user': str(user), 'notifications': serializer.data})
