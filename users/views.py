# users/views.py
import json
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.models import Group, Permission
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.views.decorators.http import require_POST, require_GET
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import serializers

User = get_user_model()


# ─── Serializers ────────────────────────────────────────────────

class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']


class UserListSerializer(serializers.ModelSerializer):
    groups    = GroupSerializer(many=True, read_only=True)
    full_name = serializers.SerializerMethodField()
    # Nombres de los grupos para que el frontend los use como roles
    group_names = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email',
            'first_name', 'last_name', 'full_name',
            'is_active', 'is_staff', 'is_superuser',
            'last_login', 'date_joined',
            'groups', 'group_names',
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_group_names(self, obj):
        return list(obj.groups.values_list('name', flat=True))


class UserWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    groups   = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), many=True, required=False
    )

    class Meta:
        model = User
        fields = [
            'username', 'email',
            'first_name', 'last_name',
            'is_active', 'is_staff',
            'password', 'groups',
        ]

    def create(self, validated_data):
        groups   = validated_data.pop('groups', [])
        password = validated_data.pop('password', None)
        user     = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        if groups:
            user.groups.set(groups)
        return user

    def update(self, instance, validated_data):
        groups   = validated_data.pop('groups', None)
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if groups is not None:
            instance.groups.set(groups)
        return instance


# ─── ViewSets ───────────────────────────────────────────────────

class UserViewSet(viewsets.ModelViewSet):
    """
    CRUD de usuarios del tenant.
    GET    /api/usuarios/              lista
    POST   /api/usuarios/              crear usuario
    PATCH  /api/usuarios/{id}/         editar
    DELETE /api/usuarios/{id}/         eliminar (solo si no es el propio usuario)
    POST   /api/usuarios/{id}/activar/     → is_active = True
    POST   /api/usuarios/{id}/desactivar/  → is_active = False
    POST   /api/usuarios/{id}/reset_password/  → nueva contraseña
    GET    /api/usuarios/me/           perfil del usuario autenticado
    """
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['username', 'email', 'first_name', 'last_name']
    ordering           = ['username']

    def get_queryset(self):
        qs = User.objects.prefetch_related('groups').order_by('username')
        activo = self.request.query_params.get('activo')
        if activo is not None:
            qs = qs.filter(is_active=(activo.lower() in ('1', 'true')))
        return qs

    def get_serializer_class(self):
        if self.action in ('list', 'retrieve', 'me'):
            return UserListSerializer
        return UserWriteSerializer

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            return Response(
                {'error': 'No podés eliminar tu propio usuario.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if user.is_superuser:
            return Response(
                {'error': 'No se puede eliminar un superusuario.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Perfil del usuario autenticado."""
        serializer = UserListSerializer(request.user)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def activar(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response({'ok': True, 'is_active': True})

    @action(detail=True, methods=['post'])
    def desactivar(self, request, pk=None):
        user = self.get_object()
        if user == request.user:
            return Response({'error': 'No podés desactivar tu propio usuario.'}, status=400)
        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response({'ok': True, 'is_active': False})

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        """Cambiar la contraseña de un usuario."""
        user = self.get_object()
        new_password = request.data.get('password', '')
        if len(new_password) < 8:
            return Response({'error': 'La contraseña debe tener al menos 8 caracteres.'}, status=400)
        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'ok': True})


class GroupViewSet(viewsets.ModelViewSet):
    """
    CRUD de grupos/roles.
    GET    /api/grupos/
    POST   /api/grupos/
    PATCH  /api/grupos/{id}/
    DELETE /api/grupos/{id}/
    """
    queryset           = Group.objects.all().order_by('name')
    permission_classes = [IsAuthenticated]
    filter_backends    = [filters.SearchFilter]
    search_fields      = ['name']

    def get_serializer_class(self):
        return GroupSerializer


# ─── Vistas legacy (CSRF/session) ───────────────────────────────

@ensure_csrf_cookie
def get_csrf_token(request):
    return JsonResponse({'csrfToken': get_token(request)})


@require_POST
def login_view(request):
    try:
        data     = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        user     = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({
                'success': True,
                'user': {
                    'id':          user.id,
                    'username':    user.username,
                    'email':       user.email,
                    'full_name':   user.get_full_name(),
                    'is_superuser':user.is_superuser,
                    'groups':      list(user.groups.values_list('name', flat=True)),
                    'permissions': list(user.get_all_permissions()),
                }
            })
        return JsonResponse({'success': False, 'error': 'Credenciales inválidas'}, status=401)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({'success': True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_info_view(request):
    """
    Retorna el perfil del usuario autenticado.
    Compatible con JWT (Authorization: Bearer <token>) Y sesión Django.
    """
    user = request.user
    return Response({
        'is_logged_in': True,
        'user': {
            'id':           user.id,
            'username':     user.username,
            'email':        user.email,
            'first_name':   user.first_name,
            'last_name':    user.last_name,
            'full_name':    user.get_full_name() or user.username,
            'is_active':    user.is_active,
            'is_staff':     user.is_staff,
            'is_superuser': user.is_superuser,
            'last_login':   user.last_login.isoformat() if user.last_login else None,
            'date_joined':  user.date_joined.isoformat(),
            'groups':       list(user.groups.values('id', 'name')),
            'group_names':  list(user.groups.values_list('name', flat=True)),
            'permissions':  list(user.get_all_permissions()),
        }
    })
    return JsonResponse({'is_logged_in': False})