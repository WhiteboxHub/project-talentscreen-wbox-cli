<template>
  <div class="apply-job-container bg-gray-50 min-h-screen p-8">
    <div class="max-w-4xl mx-auto">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-3xl font-bold text-gray-900 mb-2">Auto Job Application</h1>
        <p class="text-gray-600">Paste a job link and watch it apply in real-time</p>
      </div>

      <!-- Input Section -->
      <div class="bg-white rounded-lg shadow-md p-6 mb-8">
          <div class="flex gap-2">
          <input
            v-model="jobUrl"
            type="url"
            placeholder="Paste job URL (e.g., https://...)"
            class="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            @keyup.enter="startApplication"
            :disabled="isApplying"
          />
          <button
            @click="startApplication"
            :disabled="!jobUrl || isApplying"
            class="px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition"
          >
            {{ isApplying ? 'Applying...' : 'Apply Now' }}
          </button>
        </div>
        <p v-if="sessionId" class="text-sm text-gray-500 mt-2">Session ID: {{ sessionId }}</p>
      </div>

      <!-- Session Status -->
      <div v-if="sessionId" class="bg-white rounded-lg shadow-md p-6 mb-8">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Application Status</h2>
        <div class="grid grid-cols-2 gap-4">
          <div class="bg-blue-50 p-4 rounded-lg">
            <p class="text-sm text-gray-600">Status</p>
            <p class="text-lg font-semibold text-blue-600 capitalize">{{ currentStatus }}</p>
          </div>
          <div class="bg-green-50 p-4 rounded-lg">
            <p class="text-sm text-gray-600">Events Logged</p>
            <p class="text-lg font-semibold text-green-600">{{ eventLog.length }}</p>
          </div>
        </div>
      </div>

      <!-- Waiting for User Input -->
      <div v-if="waitingForInput" class="bg-yellow-50 border-2 border-yellow-200 rounded-lg p-6 mb-8">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Bot Needs Your Input</h2>
        <div class="bg-white p-4 rounded-lg mb-4">
          <p class="text-gray-700 font-medium">{{ currentQuestion?.text || 'Please provide information' }}</p>
        </div>

        <!-- Multiple Choice -->
        <div v-if="currentQuestion?.options && currentQuestion.options.length > 0" class="mb-4">
          <div class="space-y-2">
            <label
              v-for="(option, index) in currentQuestion.options"
              :key="index"
              class="flex items-center p-3 border border-gray-300 rounded-lg cursor-pointer hover:bg-gray-50"
            >
              <input
                type="radio"
                :value="option"
                v-model="userAnswer"
                class="mr-3"
              />
              <span class="text-gray-700">{{ option }}</span>
            </label>
          </div>
        </div>

        <!-- Text Input -->
          <div v-else class="mb-4">
          <input
            v-model="userAnswer"
            type="text"
            placeholder="Enter your answer"
            class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500"
            @keyup.enter="submitAnswer"
          />
        </div>

        <button
          @click="submitAnswer"
          :disabled="!userAnswer"
          class="w-full px-4 py-3 bg-yellow-600 text-white rounded-lg font-semibold hover:bg-yellow-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition"
        >
          Submit Answer
        </button>
      </div>

      <!-- Event Log -->
      <div v-if="eventLog.length > 0" class="bg-white rounded-lg shadow-md p-6 mb-8">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Event Log ({{ eventLog.length }})</h2>
        <div class="space-y-2 max-h-80 overflow-y-auto">
          <div
            v-for="(event, index) in eventLog"
            :key="index"
            class="p-3 bg-gray-50 rounded-lg border-l-4"
            :class="getEventColorClass(event.type)"
          >
            <div class="flex justify-between items-start">
              <div>
                <p class="font-semibold text-gray-800" :class="getEventTextColor(event.type)">{{ event.type }}</p>
                <p v-if="event.details" class="text-sm text-gray-600 mt-1">{{ event.details }}</p>
              </div>
              <span class="text-xs text-gray-500">{{ formatTime(event.timestamp) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Completion Message -->
      <div v-if="isCompleted" class="bg-green-50 border-2 border-green-200 rounded-lg p-6 mb-8">
        <div class="flex items-center gap-3 mb-2">
          <span class="text-3xl">✓</span>
          <h2 class="text-lg font-semibold text-green-800">Application Completed!</h2>
        </div>
        <p class="text-green-700">The job application has been successfully submitted.</p>
      </div>

      <!-- Error Message -->
      <div v-if="errorMessage" class="bg-red-50 border-2 border-red-200 rounded-lg p-6 mb-8">
        <div class="flex items-center gap-3 mb-2">
          <span class="text-3xl">✕</span>
          <h2 class="text-lg font-semibold text-red-800">Application Error</h2>
        </div>
        <p class="text-red-700">{{ errorMessage }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Event {
  type: string
  details?: string
  timestamp: Date
}

interface Question {
  text: string
  options?: string[]
  field_name?: string
}

const jobUrl = ref('')
const sessionId = ref('')
const isApplying = ref(false)
const currentStatus = ref('idle')
const eventLog = ref<Event[]>([])
const waitingForInput = ref(false)
const currentQuestion = ref<Question | null>(null)
const userAnswer = ref('')
const isCompleted = ref(false)
const errorMessage = ref('')
let eventSource: EventSource | null = null

const startApplication = async () => {
  if (!jobUrl.value) return

  isApplying.value = true
  errorMessage.value = ''
  isCompleted.value = false
  eventLog.value = []
  waitingForInput.value = false

  try {
    const response = await fetch('/api/apply/with-ui', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: jobUrl.value })
    })

    const data = await response.json()
    sessionId.value = data.session_id
    currentStatus.value = 'starting'

    listenToEvents()
  } catch (error) {
    errorMessage.value = `Failed to start application: ${error}`
    isApplying.value = false
  }
}

const listenToEvents = () => {
  if (eventSource) eventSource.close()

  eventSource = new EventSource(`/api/apply/session/${sessionId.value}`)

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)

    if (data.event_type === 'question') {
      waitingForInput.value = true
      currentQuestion.value = {
        text: data.question_text,
        options: data.options,
        field_name: data.field_name
      }
      currentStatus.value = 'waiting_for_input'

      eventLog.value.push({
        type: 'question',
        details: data.question_text,
        timestamp: new Date()
      })
    } else if (data.event_type === 'user_input_received') {
      waitingForInput.value = false
      currentQuestion.value = null
      userAnswer.value = ''
      currentStatus.value = 'continuing'

      eventLog.value.push({
        type: 'input_received',
        details: data.answer,
        timestamp: new Date()
      })
    } else if (data.event_type === 'completed') {
      isCompleted.value = true
      isApplying.value = false
      currentStatus.value = 'completed'
      eventSource?.close()

      eventLog.value.push({
        type: 'completed',
        details: 'Application submitted successfully',
        timestamp: new Date()
      })
    } else if (data.event_type === 'error') {
      errorMessage.value = data.error_message
      isApplying.value = false
      currentStatus.value = 'error'
      eventSource?.close()

      eventLog.value.push({
        type: 'error',
        details: data.error_message,
        timestamp: new Date()
      })
    } else {
      currentStatus.value = data.status || currentStatus.value

      eventLog.value.push({
        type: data.event_type || 'unknown',
        details: data.details || JSON.stringify(data),
        timestamp: new Date()
      })
    }
  }

  eventSource.onerror = () => {
    errorMessage.value = 'Lost connection to server'
    isApplying.value = false
    eventSource?.close()
  }
}

const submitAnswer = async () => {
  if (!userAnswer.value) return

  try {
    await fetch('/api/apply/user-input', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId.value,
        field_name: currentQuestion.value?.field_name,
        value: userAnswer.value
      })
    })
  } catch (error) {
    errorMessage.value = `Failed to submit answer: ${error}`
  }
}

const getEventColorClass = (eventType: string) => {
  switch (eventType) {
    case 'field_filled':
      return 'border-blue-500 bg-blue-50'
    case 'button_clicked':
      return 'border-purple-500 bg-purple-50'
    case 'question':
      return 'border-yellow-500 bg-yellow-50'
    case 'completed':
      return 'border-green-500 bg-green-50'
    case 'error':
      return 'border-red-500 bg-red-50'
    default:
      return 'border-gray-300'
  }
}

const getEventTextColor = (eventType: string) => {
  switch (eventType) {
    case 'field_filled':
      return 'text-blue-700'
    case 'button_clicked':
      return 'text-purple-700'
    case 'question':
      return 'text-yellow-700'
    case 'completed':
      return 'text-green-700'
    case 'error':
      return 'text-red-700'
    default:
      return 'text-gray-700'
  }
}

const formatTime = (date: Date) => {
  return new Date(date).toLocaleTimeString()
}
</script>

<style scoped>
.apply-job-container {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* Smooth transitions */
button {
  transition: all 0.2s ease;
}

input:disabled {
  background-color: #f3f4f6;
  cursor: not-allowed;
}

/* Event log scrollbar styling */
::-webkit-scrollbar {
  width: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f5f9;
}

::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
