from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class PublicUserSerializer(serializers.ModelSerializer):
    """Ulanyjy barada umumy maglumat (parolsyz). Awtoulag, taryh, profil jogaplarynda ulanylýar."""
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role', 'phone_number', 'created_at']
        read_only_fields = fields


class ProfileSerializer(serializers.ModelSerializer):
    """Öz profilim: ady, telefony, e-poçtasy we Telegram chat ID üýtgedilip bilner."""
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role', 'phone_number',
                  'telegram_chat_id', 'created_at']
        read_only_fields = ['id', 'username', 'role', 'created_at']


class UserSerializer(serializers.ModelSerializer):
    """Admin üçin işgärler sanawy. Parollar saklanmaýar — diňe döredilende / täzelenende bir gezek görkezilýär."""
    vehicles_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role', 'phone_number',
                  'telegram_chat_id', 'is_active', 'vehicles_count', 'created_at']
        read_only_fields = ['id', 'username', 'created_at', 'role', 'vehicles_count']

    def get_vehicles_count(self, obj):
        return obj.assigned_vehicles.count()


class EmployeeCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=30, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value


class EmployeeCreatedResponseSerializer(serializers.ModelSerializer):
    generated_password = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role', 'phone_number', 'generated_password', 'created_at']


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs['old_password']):
            raise serializers.ValidationError({"old_password": "Häzirki parol nädogry."})
        if attrs['old_password'] == attrs['new_password']:
            raise serializers.ValidationError({"new_password": "Täze parol köne paroldan tapawutly bolmaly."})
        validate_password(attrs['new_password'], user)
        return attrs
