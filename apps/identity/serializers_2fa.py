from rest_framework import serializers

class Confirm2FASerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6)

class Login2FASerializer(serializers.Serializer):
    temp_token = serializers.CharField()
    code = serializers.CharField(required=False, help_text="TOTP code (6 digits)")
    backup_code = serializers.CharField(required=False, help_text="One-time backup code")

    def validate(self, attrs):
        if not attrs.get('code') and not attrs.get('backup_code'):
            raise serializers.ValidationError("Either 'code' (TOTP) or 'backup_code' must be provided.")
        return attrs

class Disable2FASerializer(serializers.Serializer):
    password = serializers.CharField()
