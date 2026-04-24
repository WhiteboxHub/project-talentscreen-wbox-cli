/**
 * REAL-TIME JOB APPLICATION UI INTEGRATION GUIDE
 * 
 * This guide explains how to integrate the new real-time application API
 * endpoints with your Vue.js UI to show live application progress.
 */

// ============================================================================
// 1. UPDATED API ENDPOINTS
// ============================================================================

const API_BASE = 'http://localhost:8000/api';

/**
 * POST /api/apply/with-ui
 * 
 * Starts a job application with real-time UI updates
 * Returns: { session_id, message, url }
 * 
 * Usage:
 *   const response = await fetch(`${API_BASE}/apply/with-ui`, {
 *     method: 'POST',
 *     headers: { 'Content-Type': 'application/json' },
 *     body: JSON.stringify({ url: 'https://example.com/job' })
 *   });
 *   const { session_id } = await response.json();
 */

/**
 * POST /api/apply/user-input
 * 
 * Submit user input when application pauses to ask a question
 * 
 * Usage:
 *   await fetch(`${API_BASE}/apply/user-input`, {
 *     method: 'POST',
 *     headers: { 'Content-Type': 'application/json' },
 *     body: JSON.stringify({
 *       session_id: 'abc123',
 *       field_name: 'work_authorization',
 *       value: 'Yes, authorized'
 *     })
 *   });
 */

/**
 * GET /api/apply/session/{session_id}
 * 
 * Get current status of an application session
 * Returns: { status, url, paused, waiting_for, events_count }
 */

// ============================================================================
// 2. WEBSOCKET MESSAGES - NEW APPLICATION EVENTS
// ============================================================================

/**
 * The WebSocket at /ws will now broadcast these new event types:
 */

// Event 1: Application started
{
  "type": "application_event",
  "session_id": "abc123",
  "event": "started",
  "url": "https://example.com/job",
  "message": "🚀 Starting application to https://example.com/job"
}

// Event 2: Form field being filled
{
  "type": "application_event",
  "session_id": "abc123",
  "event": "field_filled",
  "field": "first_name",
  "value": "John",
  "message": "✓ Filled: First Name = John"
}

// Event 3: Button clicked
{
  "type": "application_event",
  "session_id": "abc123",
  "event": "button_clicked",
  "button": "Next",
  "message": "→ Clicked: Next"
}

// Event 4: Question requiring user input
{
  "type": "application_event",
  "session_id": "abc123",
  "event": "question",
  "field": "years_experience",
  "question": "How many years of experience do you have?",
  "options": ["0-1", "1-3", "3-5", "5+"],
  "message": "❓ Requires input: How many years of experience do you have?"
}

// Event 5: User input received
{
  "type": "application_event",
  "session_id": "abc123",
  "event": "user_input_received",
  "field": "years_experience",
  "value": "5+",
  "message": "✓ Received: years_experience = 5+"
}

// Event 6: Page navigated
{
  "type": "application_event",
  "session_id": "abc123",
  "event": "page_changed",
  "url": "https://example.com/job/apply/step2",
  "title": "Application - Step 2",
  "message": "📄 Navigated to: Application - Step 2"
}

// Event 7: Application completed
{
  "type": "application_event",
  "session_id": "abc123",
  "event": "completed",
  "message": "✅ Application submitted successfully!"
}

// Event 8: Error occurred
{
  "type": "application_event",
  "session_id": "abc123",
  "event": "error",
  "error": "Form validation failed",
  "message": "❌ Error: Form validation failed"
}

// ============================================================================
// 3. VUE COMPONENT EXAMPLE
// ============================================================================

/**
 * ApplyJobComponent.vue - Shows application in progress
 */

<template>
  <div class="apply-container">
    <!-- URL Input -->
    <div class="input-section" v-if="!sessionId">
      <input 
        v-model="jobUrl" 
        type="url"
        placeholder="Paste job URL here..."
        @keyup.enter="startApplication"
      />
      <button @click="startApplication" :disabled="!jobUrl">
        🚀 Apply Now
      </button>
    </div>

    <!-- Application Progress -->
    <div v-if="sessionId" class="progress-section">
      <div class="session-info">
        <h3>Applying to: {{ sessionStatus.url }}</h3>
        <p>Session: {{ sessionId }}</p>
        <p>Status: {{ sessionStatus.status }}</p>
      </div>

      <!-- Event Log -->
      <div class="event-log">
        <div v-for="(event, idx) in events" :key="idx" class="event-item">
          <span class="event-icon">{{ getEventIcon(event.event) }}</span>
          <span class="event-message">{{ event.message }}</span>
          <span class="event-time">{{ formatTime(event.timestamp) }}</span>
        </div>
      </div>

      <!-- User Input Section (when paused) -->
      <div v-if="currentQuestion" class="question-section">
        <h4>{{ currentQuestion.question }}</h4>
        
        <!-- Options (if available) -->
        <div v-if="currentQuestion.options" class="options">
          <button
            v-for="option in currentQuestion.options"
            :key="option"
            @click="submitAnswer(option)"
            class="option-btn"
          >
            {{ option }}
          </button>
        </div>

        <!-- Text Input (if open-ended) -->
        <div v-else class="text-input">
          <input
            v-model="userAnswer"
            type="text"
            :placeholder="`Enter ${currentQuestion.field}...`"
            @keyup.enter="submitAnswer(userAnswer)"
          />
          <button @click="submitAnswer(userAnswer)">
            Submit
          </button>
        </div>
      </div>

      <!-- Completion Message -->
      <div v-if="sessionStatus.status === 'completed'" class="success">
        ✅ Application submitted successfully!
      </div>
      <div v-if="sessionStatus.status === 'error'" class="error">
        ❌ Application failed: {{ sessionStatus.error }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue';

const API_BASE = 'http://localhost:8000/api';

// State
const jobUrl = ref('');
const sessionId = ref('');
const events = ref<any[]>([]);
const currentQuestion = ref<any>(null);
const userAnswer = ref('');
const sessionStatus = reactive({
  url: '',
  status: 'idle',
  paused: false,
  waiting_for: null,
  error: ''
});

// Start application
async function startApplication() {
  if (!jobUrl.value) return;

  try {
    const response = await fetch(`${API_BASE}/apply/with-ui`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: jobUrl.value })
    });
    
    const data = await response.json();
    sessionId.value = data.session_id;
    sessionStatus.url = data.url;
    sessionStatus.status = 'running';
    
    // Start listening to events
    listenToEvents();
  } catch (err) {
    console.error('Error starting application:', err);
    sessionStatus.error = String(err);
  }
}

// Listen to WebSocket events
function listenToEvents() {
  const ws = new WebSocket('ws://localhost:8000/ws');
  
  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data);
      
      if (message.type === 'application_event' && 
          message.session_id === sessionId.value) {
        
        // Add to event log
        events.value.push({
          ...message,
          timestamp: new Date()
        });

        // Update status
        if (message.status) {
          sessionStatus.status = message.status;
        }

        // Handle question
        if (message.event === 'question') {
          currentQuestion.value = message;
          sessionStatus.paused = true;
          sessionStatus.waiting_for = message.field;
        } else if (message.event === 'user_input_received') {
          currentQuestion.value = null;
          userAnswer.value = '';
          sessionStatus.paused = false;
          sessionStatus.waiting_for = null;
        }

        // Handle completion
        if (message.event === 'completed') {
          sessionStatus.status = 'completed';
        } else if (message.event === 'error') {
          sessionStatus.status = 'error';
          sessionStatus.error = message.message;
        }
      }
    } catch (err) {
      console.error('Error parsing WebSocket message:', err);
    }
  };
}

// Submit user answer
async function submitAnswer(value: string) {
  if (!sessionId.value || !currentQuestion.value) return;

  try {
    await fetch(`${API_BASE}/apply/user-input`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId.value,
        field_name: currentQuestion.value.field,
        value: value
      })
    });

    // Clear answer
    userAnswer.value = '';
  } catch (err) {
    console.error('Error submitting answer:', err);
  }
}

// Helper functions
function getEventIcon(eventType: string): string {
  const icons: Record<string, string> = {
    'started': '🚀',
    'field_filled': '✓',
    'button_clicked': '→',
    'question': '❓',
    'user_input_received': '✓',
    'page_changed': '📄',
    'completed': '✅',
    'error': '❌'
  };
  return icons[eventType] || '•';
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString();
}
</script>

<style scoped>
.apply-container {
  max-width: 800px;
  margin: 20px auto;
  font-family: monospace;
}

.input-section {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.input-section input {
  flex: 1;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.input-section button {
  padding: 10px 20px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.progress-section {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  background: #f9f9f9;
}

.session-info {
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid #ddd;
}

.session-info h3 {
  margin: 0 0 5px 0;
}

.session-info p {
  margin: 5px 0;
  font-size: 12px;
  color: #666;
}

.event-log {
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
  margin-bottom: 20px;
}

.event-item {
  display: flex;
  padding: 10px;
  border-bottom: 1px solid #eee;
  font-size: 13px;
}

.event-icon {
  margin-right: 10px;
  min-width: 20px;
}

.event-message {
  flex: 1;
}

.event-time {
  color: #999;
  font-size: 11px;
  margin-left: 10px;
}

.question-section {
  background: white;
  border: 2px solid #ff9800;
  border-radius: 4px;
  padding: 15px;
  margin-bottom: 20px;
}

.question-section h4 {
  margin: 0 0 15px 0;
}

.options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  gap: 10px;
}

.option-btn {
  padding: 10px;
  background: #f0f0f0;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.option-btn:hover {
  background: #e0e0e0;
}

.text-input {
  display: flex;
  gap: 10px;
}

.text-input input {
  flex: 1;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.text-input button {
  padding: 8px 15px;
  background: #28a745;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.success, .error {
  padding: 15px;
  border-radius: 4px;
  text-align: center;
  font-weight: bold;
}

.success {
  background: #d4edda;
  color: #155724;
  border: 1px solid #c3e6cb;
}

.error {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}
</style>

// ============================================================================
// 4. KEY FEATURES
// ============================================================================

/**
 * ✅ Real-time Updates
 *    - Every action is broadcast to the UI via WebSocket
 *    - Users see exactly what the bot is doing
 *
 * ✅ User Input Support
 *    - When bot encounters a field it can't auto-fill
 *    - Application pauses and asks user in the UI
 *    - User submits answer and bot continues
 *
 * ✅ Session Tracking
 *    - Each application has a unique session_id
 *    - Can track multiple concurrent applications
 *    - Query session status at any time
 *
 * ✅ Detailed Event Log
 *    - Every step is logged with timestamp
 *    - Users can review application progress
 *    - Helps debug issues
 *
 * ✅ Error Handling
 *    - Errors are caught and displayed
 *    - Application stops gracefully
 *    - Users see exactly what went wrong
 */

// ============================================================================
// 5. INTEGRATION STEPS
// ============================================================================

/**
 * 1. Copy the Vue component (ApplyJobComponent.vue) into your ui/src/components
 * 
 * 2. Import and use in your main page:
 *    import ApplyJobComponent from '@/components/ApplyJobComponent.vue';
 *    // Then use: <ApplyJobComponent />
 * 
 * 3. The component handles everything:
 *    - Accepts URL from user
 *    - Starts application
 *    - Listens to events
 *    - Shows progress
 *    - Prompts for user input
 *    - Displays results
 * 
 * 4. Backend automatically sends events through WebSocket
 *    - No additional code needed in backend
 *    - Events are broadcast to all connected clients
 */

// ============================================================================
// 6. WORKFLOW EXAMPLE
// ============================================================================

/**
 * User: Pastes link → Clicks "Apply Now"
 *   ↓
 * API: /api/apply/with-ui receives request
 *   ↓
 * Backend: Starts application process
 *   ↓
 * Backend: Broadcasts "started" event
 *   ↓
 * UI: Shows "🚀 Starting application..."
 *   ↓
 * Backend: Bot fills "First Name" field
 *   ↓
 * Backend: Broadcasts "field_filled" event
 *   ↓
 * UI: Shows "✓ Filled: First Name = John"
 *   ↓
 * Backend: Bot encounters "Work Authorization" field
 * Backend: Can't auto-fill (needs user decision)
 *   ↓
 * Backend: Broadcasts "question" event with options
 *   ↓
 * UI: Shows question with options
 *   ↓
 * User: Selects "Yes, authorized"
 *   ↓
 * UI: Sends to /api/apply/user-input
 *   ↓
 * Backend: Receives answer via session_input_queues
 *   ↓
 * Backend: Application resumes with answer
 *   ↓
 * Backend: Bot fills field and continues
 *   ↓
 * ... (repeat until form complete)
 *   ↓
 * Backend: Bot clicks "Submit"
 *   ↓
 * Backend: Broadcasts "completed" event
 *   ↓
 * UI: Shows "✅ Application submitted successfully!"
 */

// ============================================================================
// 7. NEXT STEPS
// ============================================================================

/**
 * To enable this in your application:
 * 
 * 1. The API endpoints are already added to main.py
 * 
 * 2. Copy the Vue component to your UI
 * 
 * 3. Update your engine.py to emit events:
 *    - When filling a field → emit "field_filled" event
 *    - When clicking button → emit "button_clicked" event
 *    - When asking user → emit "question" event
 *    - When receiving answer → emit "user_input_received" event
 * 
 * 4. Connect the engine to session_input_queues to get user answers
 * 
 * 5. Test with a sample job URL
 */
