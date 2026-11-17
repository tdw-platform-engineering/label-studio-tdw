"""This file and its contents are licensed under the Apache License 2.0. Please see the included NOTICE for copyright information and LICENSE for a copy of the license.
"""
import re

from core.utils.io import validate_upload_url
from django.conf import settings
from drf_spectacular.utils import extend_schema_field
from ml.models import MLBackend, MLBackendAuth
from rest_framework import serializers


class MLBackendSerializer(serializers.ModelSerializer):
    """
    Serializer for MLBackend model.
    """

    readable_state = serializers.SerializerMethodField()
    basic_auth_pass = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    basic_auth_pass_is_set = serializers.SerializerMethodField()
    # TDW patch: API key auth. The key is write-only, like the Basic auth password.
    api_key = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    api_key_is_set = serializers.SerializerMethodField()

    @extend_schema_field(bool)
    def get_basic_auth_pass_is_set(self, obj):
        return bool(obj.basic_auth_pass)

    @extend_schema_field(bool)
    def get_api_key_is_set(self, obj):
        return bool(obj.api_key)

    def get_readable_state(self, obj):
        return obj.get_state_display()

    def validate_basic_auth_pass(self, value):
        # Checks if the new password and old password are non-existent.
        if not value:
            if not self.instance.basic_auth_pass:
                raise serializers.ValidationError('Authentication password is required for Basic Authentication.')
            else:
                # If user is not changing the password, return the old password.
                return self.instance.basic_auth_pass
        return value

    def validate_api_key(self, value):
        # Blank on update = keep the stored key (the UI never receives the key back).
        if not value and self.instance is not None and self.instance.api_key:
            return self.instance.api_key
        return value

    def validate_api_key_header(self, value):
        # The value becomes an HTTP header name: allow only token characters (no CR/LF, no spaces).
        value = (value or '').strip() or 'Authorization'
        if not re.fullmatch(r'[A-Za-z0-9-]{1,64}', value):
            raise serializers.ValidationError('Header name may contain only letters, digits and "-".')
        return value

    def validate_url(self, value):
        validate_upload_url(value, block_local_urls=settings.ML_BLOCK_LOCAL_IP)

        return value

    def _validate_authentication(self, attrs):
        if attrs.get('auth_method') == MLBackendAuth.BASIC_AUTH:
            required_fields = ['basic_auth_user', 'basic_auth_pass']

            if any(field not in attrs for field in required_fields):
                raise serializers.ValidationError(
                    'Authentication username and password is required for Basic Authentication.'
                )

        if attrs.get('auth_method') == MLBackendAuth.API_KEY:
            if not attrs.get('api_key') and self.instance is not None:
                attrs['api_key'] = self.instance.api_key  # keep the stored key on update
            if not attrs.get('api_key'):
                raise serializers.ValidationError('API key is required for API Key authentication.')

    def _validate_healthcheck(self, attrs):
        healthcheck_response = MLBackend.healthcheck_(**attrs)

        if healthcheck_response.is_error:
            if healthcheck_response.status_code == 401:
                message = (
                    'Able to connect to ML Server, but authentication parameters were '
                    'either not provided or are incorrect.'
                )
            else:
                message = (
                    f"Can't connect to ML backend {attrs['url']}, health check failed. "
                    'Make sure it is up and your firewall is properly configured. '
                    f'<a href="https://labelstud.io/guide/ml.html">Learn more</a> '
                    f'about how to set up an ML backend. Additional info: {healthcheck_response.error_message}'
                )

            raise serializers.ValidationError(message)

    def _validate_setup(self, attrs):
        setup_response = MLBackend.setup_(**attrs)

        if setup_response.is_error:
            message = (
                f"Successfully connected to {attrs['url']} but it doesn't look like a valid ML backend. "
                f'Reason: {setup_response.error_message}.\n'
                'Check the ML backend server console logs to check the status.'
                'There might be something wrong with your model or it might be incompatible with the current labeling configuration.'
            )

            raise serializers.ValidationError(message)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        self._validate_authentication(attrs)
        self._validate_healthcheck(attrs)
        self._validate_setup(attrs)

        return attrs

    class Meta:
        model = MLBackend
        fields = [
            'id',
            'state',
            'readable_state',
            'is_interactive',
            'url',
            'error_message',
            'title',
            'auth_method',
            'basic_auth_user',
            'basic_auth_pass',
            'basic_auth_pass_is_set',
            'api_key',
            'api_key_header',
            'api_key_is_set',
            'description',
            'extra_params',
            'model_version',
            'timeout',
            'created_at',
            'updated_at',
            'auto_update',
            'project',
        ]


class MLInteractiveAnnotatingRequest(serializers.Serializer):
    """
    Serializer for ML interactive annotating request.
    """

    task = serializers.IntegerField(help_text='ID of task to annotate', required=True)
    context = serializers.JSONField(help_text='Context for ML model', allow_null=True, default=None)
