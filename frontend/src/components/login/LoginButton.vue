<template>
  <button class="btn" :disabled="loading || disabled" type="button" @click="$emit('click')">
    <span v-if="!loading"><slot /></span>

    <span v-else class="loader" aria-hidden="true"></span>
  </button>
</template>

<script setup>
defineProps({
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
defineEmits(['click'])
</script>

<style scoped>
.btn {
  width: 100%;
  height: 48px;
  border-radius: 10px;
  border: 0;
  cursor: pointer;
  font-weight: 700;
  font-size: 16px;
  color: #fff;
  background: linear-gradient(180deg, #2f66e8, #2556cf);
  box-shadow: 0 10px 22px rgba(37, 86, 207, 0.35);
  transition:
    transform 0.12s ease,
    box-shadow 0.12s ease,
    filter 0.12s ease;
}

.btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 26px rgba(37, 86, 207, 0.42);
  filter: brightness(1.02);
}

.btn:active {
  transform: translateY(0px);
  box-shadow: 0 10px 22px rgba(37, 86, 207, 0.35);
}

.btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.loader {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  border-top-color: rgba(255, 255, 255, 1);
  display: inline-block;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
