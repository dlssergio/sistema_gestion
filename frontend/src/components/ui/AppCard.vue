<template>
  <div class="card" :class="{ clickable }" @click="$emit('click')">
    <div v-if="$slots.header" class="header">
      <slot name="header" />
    </div>

    <div class="body">
      <slot />
    </div>

    <div v-if="$slots.footer" class="footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup>
defineProps({
  clickable: { type: Boolean, default: false },
})
defineEmits(['click'])
</script>

<style scoped>
.card {
  background: var(--surface-1, #ffffff);
  border: 1px solid var(--border, rgba(15, 23, 42, 0.1));
  border-radius: var(--radius-lg, 10px);
  box-shadow: var(--card-shadow, 0 10px 24px rgba(2, 6, 23, 0.1));
  overflow: hidden;

  /* Cortar cualquier halo heredado */
  filter: none !important;
  outline: none !important;
}

.header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--border, rgba(15, 23, 42, 0.1));
}

.body {
  padding: 16px;
}

.footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border, rgba(15, 23, 42, 0.1));
  color: var(--text-2, #64748b);
  font-size: 13px;
}

.clickable {
  cursor: pointer;
  transition:
    transform 0.12s ease,
    box-shadow 0.12s ease;
}

.clickable:hover {
  transform: translateY(-1px);
}
</style>
