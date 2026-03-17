<template>
  <div class="field" :class="{ shake: error }">
    <label :for="id" class="label">{{ label }}</label>

    <div class="inputWrap" :class="{ error: !!error }">
      <span class="icon" aria-hidden="true">
        <!-- user -->
        <svg v-if="icon === 'user'" viewBox="0 0 24 24">
          <path
            d="M12 12c2.7 0 4.8-2.2 4.8-4.8S14.7 2.4 12 2.4 7.2 4.6 7.2 7.2 9.3 12 12 12zM12 14.4c-4 0-7.2 2-7.2 4.8v1.2h14.4v-1.2c0-2.8-3.2-4.8-7.2-4.8z"
          />
        </svg>

        <!-- lock -->
        <svg v-else viewBox="0 0 24 24">
          <path
            d="M17 8h-1V6a4 4 0 10-8 0v2H7a2 2 0 00-2 2v8a2 2 0 002 2h10a2 2 0 002-2v-8a2 2 0 00-2-2zm-6 0V6a2 2 0 114 0v2h-4z"
          />
        </svg>
      </span>

      <input
        :id="id"
        :type="actualType"
        :value="modelValue"
        @input="$emit('update:modelValue', $event.target.value)"
        @keyup.enter="$emit('enter')"
        :placeholder="label"
        autocomplete="off"
      />

      <span class="divider" aria-hidden="true"></span>

      <button
        v-if="type === 'password'"
        type="button"
        class="rightBtn"
        tabindex="-1"
        @click="showPassword = !showPassword"
        aria-label="Mostrar/Ocultar contraseña"
      >
        <svg v-if="!showPassword" viewBox="0 0 24 24">
          <path
            d="M3 3l18 18M10.6 10.6a2.5 2.5 0 003.5 3.5M9.5 5.5A10.5 10.5 0 0121 12a10.6 10.6 0 01-3.5 4.6M6.2 6.2A10.6 10.6 0 003 12a10.5 10.5 0 006.3 6.1A10.6 10.6 0 0012 19c1.2 0 2.3-.2 3.4-.6"
          />
        </svg>
        <svg v-else viewBox="0 0 24 24">
          <path
            d="M12 5c5 0 9.3 3 10.7 7-1.4 4-5.7 7-10.7 7S2.7 16 1.3 12C2.7 8 7 5 12 5zm0 3.2A3.8 3.8 0 1015.8 12 3.8 3.8 0 0012 8.2z"
          />
        </svg>
      </button>

      <span v-else class="rightIcon" aria-hidden="true">
        <svg viewBox="0 0 24 24">
          <path d="M10 18a8 8 0 115.3-14l5.7 5.7-1.4 1.4-1.7-1.7V20h-2V7.4A6 6 0 1010 16v2z" />
        </svg>
      </span>
    </div>

    <p v-if="error" class="errorText">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  label: { type: String, required: true },
  modelValue: { type: [String, Number], default: '' },
  type: { type: String, default: 'text' },
  icon: { type: String, default: 'user' }, // 'user' | 'lock'
  error: { type: String, default: '' },
})

defineEmits(['update:modelValue', 'enter'])

const showPassword = ref(false)

const actualType = computed(() => {
  if (props.type === 'password') return showPassword.value ? 'text' : 'password'
  return props.type
})
</script>

<style scoped>
.field {
  position: relative;
}

.label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.inputWrap {
  position: relative;
  display: flex;
  align-items: center;
  height: 44px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  background: #fff;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.inputWrap:focus-within {
  border-color: #93c5fd;
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1);
}

.inputWrap.error {
  border-color: #fca5a5;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.1);
}

.icon {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  opacity: 0.65;
}

.icon svg {
  width: 18px;
  height: 18px;
  fill: #6b7280;
}

input {
  flex: 1;
  height: 100%;
  border: 0;
  outline: none;
  font-size: 14px;
  color: #111827;
  background: transparent;
}

.divider {
  width: 1px;
  height: 60%;
  background: #e5e7eb;
}

.rightBtn,
.rightIcon {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  background: transparent;
  border: 0;
  cursor: pointer;
  opacity: 0.65;
}

.rightBtn svg,
.rightIcon svg {
  width: 18px;
  height: 18px;
  fill: #6b7280;
}

.errorText {
  margin-top: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #dc2626;
}

@keyframes shake {
  0%,
  100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-3px);
  }
  50% {
    transform: translateX(3px);
  }
  75% {
    transform: translateX(-3px);
  }
}

.shake {
  animation: shake 0.3s cubic-bezier(0.36, 0.07, 0.19, 0.97);
}
</style>
