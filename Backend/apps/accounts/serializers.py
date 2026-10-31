from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """The signed-in user."""

    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'display_name', 'is_staff']
        read_only_fields = ['username', 'is_staff']

    def validate_email(self, email):
        if User.objects.filter(email__iexact=email).exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError('An account with this email address already exists.')
        return email.lower()


class PublicUserSerializer(serializers.ModelSerializer):
    """What teammates see about a user."""

    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'display_name', 'email']


class AccountCreateSerializer(serializers.ModelSerializer):
    """New account details, checked with Django's password validators."""

    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name', 'last_name']

    def validate_email(self, email):
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('An account with this email address already exists.')
        return email.lower()

    def validate(self, attrs):
        try:
            password_validation.validate_password(attrs['password'], User(username=attrs['username'], email=attrs['email']))
        except DjangoValidationError as error:
            raise serializers.ValidationError({'password': list(error.messages)})
        return attrs

    def create_user(self):
        return User.objects.create_user(**self.validated_data)
