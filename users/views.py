import json
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.middleware.csrf import get_token
from django.views.decorators.http import require_POST, require_GET


@ensure_csrf_cookie
def get_csrf_token(request):
    """
    Vue llamará a esto primero para obtener la cookie CSRF
    y poder hacer peticiones seguras (POST/PUT).
    """
    return JsonResponse({'csrfToken': get_token(request)})


@require_POST
def login_view(request):
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return JsonResponse({
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'full_name': user.get_full_name(),
                    # Aquí enviamos los roles y permisos a Vue
                    'is_superuser': user.is_superuser,
                    'groups': list(user.groups.values_list('name', flat=True)),
                    'permissions': list(user.get_all_permissions()),
                }
            })
        else:
            return JsonResponse({'success': False, 'error': 'Credenciales inválidas'}, status=401)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({'success': True})


@require_GET
def user_info_view(request):
    """
    Vue llama a esto al recargar la página (F5) para saber si sigue logueado.
    """
    if request.user.is_authenticated:
        return JsonResponse({
            'is_logged_in': True,
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'groups': list(request.user.groups.values_list('name', flat=True)),
                'permissions': list(request.user.get_all_permissions()),
            }
        })
    else:
        return JsonResponse({'is_logged_in': False})