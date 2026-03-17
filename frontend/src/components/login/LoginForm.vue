<template>
  <section class="form-panel">
    <div class="content">
      <div class="badge">
        <span class="dot"></span>
        Modo Demo Activo
      </div>

      <h2 class="title">Bienvenido</h2>
      <p class="sub">Iniciá sesión para continuar</p>

      <form class="form" @submit.prevent="submit">
        <LoginInput
          id="username"
          label="Usuario"
          v-model="username"
          :error="usernameError"
          icon="user"
          @enter="submit"
        />

        <LoginInput
          id="password"
          label="Contraseña"
          type="password"
          v-model="password"
          :error="passwordError"
          icon="lock"
          @enter="submit"
        />

        <p v-if="error" class="form-error">{{ error }}</p>

        <LoginButton class="btn" :loading="loading" @click="submit">Ingresar</LoginButton>
      </form>

      <p class="forgot">¿Olvidaste tu contraseña?</p>
      <div class="footer">© DEMO SA 2025</div>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import LoginInput from './LoginInput.vue'
import LoginButton from './LoginButton.vue'

const props = defineProps({
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const emit = defineEmits(['submit'])

const username = ref('')
const password = ref('')
const usernameError = ref('')
const passwordError = ref('')

const validate = () => {
  let ok = true
  usernameError.value = ''
  passwordError.value = ''

  if (!username.value.trim()) {
    usernameError.value = 'El usuario es requerido'
    ok = false
  }
  if (!password.value) {
    passwordError.value = 'La contraseña es requerida'
    ok = false
  }
  return ok
}

const submit = () => {
  if (props.loading) return
  if (!validate()) return
  emit('submit', { username: username.value.trim(), password: password.value })
}
</script>

<style scoped>
.form-panel {
  width: 460px;
  height: 100%;
  background: rgba(255, 255, 255, 0.96);
  display: flex;
  align-items: center;
  justify-content: center;
}

.content {
  width: 100%;
  padding: 56px 52px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: #e6f4ea;
  border: 1px solid #c7e9d2;
  color: #166534;
  padding: 8px 16px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 26px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #16a34a;
}

.title {
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -0.4px;
  margin: 0 0 6px 0;
  color: #111827;
}

.sub {
  margin: 0 0 28px 0;
  font-size: 14px;
  color: #6b7280;
}

.form {
  display: grid;
  gap: 16px;
}

.form-error {
  margin: 0;
  color: #dc2626;
  font-size: 13px;
  font-weight: 600;
}

.btn {
  margin-top: 6px;
}

.forgot {
  margin-top: 18px;
  text-align: center;
  color: #6b7280;
  font-size: 14px;
}

.footer {
  margin-top: 56px;
  text-align: center;
  color: #9ca3af;
  font-size: 13px;
}
</style>
