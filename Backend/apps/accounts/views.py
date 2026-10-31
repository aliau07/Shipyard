from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import User
from .serializers import AccountCreateSerializer, UserSerializer

TokenResponse = inline_serializer('TokenResponse', {'token': serializers.CharField(), 'user': UserSerializer()})


def token_response(user, status_code=status.HTTP_200_OK):
    token, _ = Token.objects.get_or_create(user=user)
    return Response({'token': token.key, 'user': UserSerializer(user).data}, status=status_code)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(style={'input_type': 'password'})


class LoginView(APIView):
    """Exchange a username (or email) and password for an API token."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    @extend_schema(request=LoginSerializer, responses=TokenResponse)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username']
        if '@' in username:
            username = User.objects.filter(email__iexact=username).values_list('username', flat=True).first() or username
        user = authenticate(request, username=username, password=serializer.validated_data['password'])
        if user is None:
            return Response({'detail': 'Invalid username or password.'}, status=status.HTTP_400_BAD_REQUEST)
        return token_response(user)


class RegisterView(APIView):
    """Anyone can sign up; they then create a project or are added to one by its owner."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    @extend_schema(request=AccountCreateSerializer, responses={201: TokenResponse})
    def post(self, request):
        serializer = AccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return token_response(serializer.create_user(), status.HTTP_201_CREATED)


class LogoutView(APIView):
    """Revoke the caller's API token."""

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """The signed-in user's details."""

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=UserSerializer, responses=UserSerializer)
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
