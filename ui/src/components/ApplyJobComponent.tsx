import React, { useState, useEffect, useRef } from 'react';

interface Event {
  type: string;
  details?: string;
  timestamp: Date;
}

interface Question {
  text: string;
  options?: string[];
  field_name?: string;
}

export const ApplyJobComponent: React.FC = () => {
  const [jobUrl, setJobUrl] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [isApplying, setIsApplying] = useState(false);
  const [currentStatus, setCurrentStatus] = useState('idle');
  const [eventLog, setEventLog] = useState<Event[]>([]);
  const [waitingForInput, setWaitingForInput] = useState(false);
  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null);
  const [userAnswer, setUserAnswer] = useState('');
  const [isCompleted, setIsCompleted] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const eventSourceRef = useRef<EventSource | null>(null);

  const startApplication = async () => {
    if (!jobUrl) return;

    setIsApplying(true);
    setErrorMessage('');
    setIsCompleted(false);
    setEventLog([]);
    setWaitingForInput(false);

    try {
      const response = await fetch('http://localhost:8000/api/apply/with-ui', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: jobUrl })
      });

      const data = await response.json();
      setSessionId(data.session_id);
      setCurrentStatus('starting');

      listenToEvents(data.session_id);
    } catch (error) {
      setErrorMessage(`Failed to start application: ${error}`);
      setIsApplying(false);
    }
  };

  const listenToEvents = (sid: string) => {
    if (eventSourceRef.current) eventSourceRef.current.close();

    eventSourceRef.current = new EventSource(`http://localhost:8000/api/apply/session/${sid}`);

    eventSourceRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.event_type === 'question') {
        setWaitingForInput(true);
        setCurrentQuestion({
          text: data.question_text,
          options: data.options,
          field_name: data.field_name
        });
        setCurrentStatus('waiting_for_input');

        setEventLog((prev) => [...prev, {
          type: 'question',
          details: data.question_text,
          timestamp: new Date()
        }]);
      } else if (data.event_type === 'user_input_received') {
        setWaitingForInput(false);
        setCurrentQuestion(null);
        setUserAnswer('');
        setCurrentStatus('continuing');

        setEventLog((prev) => [...prev, {
          type: 'input_received',
          details: data.answer,
          timestamp: new Date()
        }]);
      } else if (data.event_type === 'completed') {
        setIsCompleted(true);
        setIsApplying(false);
        setCurrentStatus('completed');
        eventSourceRef.current?.close();

        setEventLog((prev) => [...prev, {
          type: 'completed',
          details: 'Application submitted successfully',
          timestamp: new Date()
        }]);
      } else if (data.event_type === 'error') {
        setErrorMessage(data.error_message);
        setIsApplying(false);
        setCurrentStatus('error');
        eventSourceRef.current?.close();

        setEventLog((prev) => [...prev, {
          type: 'error',
          details: data.error_message,
          timestamp: new Date()
        }]);
      } else {
        setCurrentStatus(data.status || currentStatus);

        setEventLog((prev) => [...prev, {
          type: data.event_type || 'unknown',
          details: data.details || JSON.stringify(data),
          timestamp: new Date()
        }]);
      }
    };

    eventSourceRef.current.onerror = () => {
      setErrorMessage('Lost connection to server');
      setIsApplying(false);
      eventSourceRef.current?.close();
    };
  };

  const submitAnswer = async () => {
    if (!userAnswer) return;

    try {
      await fetch('http://localhost:8000/api/apply/user-input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          answer: userAnswer
        })
      });
    } catch (error) {
      setErrorMessage(`Failed to submit answer: ${error}`);
    }
  };

  const getEventColorClass = (eventType: string) => {
    switch (eventType) {
      case 'field_filled':
        return 'border-l-4 border-blue-500 bg-blue-50';
      case 'button_clicked':
        return 'border-l-4 border-purple-500 bg-purple-50';
      case 'question':
        return 'border-l-4 border-yellow-500 bg-yellow-50';
      case 'completed':
        return 'border-l-4 border-green-500 bg-green-50';
      case 'error':
        return 'border-l-4 border-red-500 bg-red-50';
      default:
        return 'border-l-4 border-gray-300 bg-gray-50';
    }
  };

  const getEventTextColor = (eventType: string) => {
    switch (eventType) {
      case 'field_filled':
        return 'text-blue-700';
      case 'button_clicked':
        return 'text-purple-700';
      case 'question':
        return 'text-yellow-700';
      case 'completed':
        return 'text-green-700';
      case 'error':
        return 'text-red-700';
      default:
        return 'text-gray-700';
    }
  };

  const formatTime = (date: Date) => {
    return new Date(date).toLocaleTimeString();
  };

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
    };
  }, []);

  return (
    <div className="apply-job-container bg-gray-50 min-h-screen p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Auto Job Application</h1>
          <p className="text-gray-600">Paste a job link and watch it apply in real-time</p>
        </div>

        {/* Input Section */}
        <div className="bg-white rounded-lg shadow-md p-6 mb-8">
          <div className="flex gap-2">
            <input
              value={jobUrl}
              onChange={(e) => setJobUrl(e.target.value)}
              type="url"
              placeholder="Paste job URL here (e.g., https://..."
              disabled={isApplying}
              onKeyUp={(e) => e.key === 'Enter' && startApplication()}
              className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            />
            <button
              onClick={startApplication}
              disabled={!jobUrl || isApplying}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition"
            >
              {isApplying ? 'Applying...' : 'Apply Now'}
            </button>
          </div>
          {sessionId && <p className="text-sm text-gray-500 mt-2">Session ID: {sessionId}</p>}
        </div>

        {/* Session Status */}
        {sessionId && (
          <div className="bg-white rounded-lg shadow-md p-6 mb-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Application Status</h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-blue-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Status</p>
                <p className="text-lg font-semibold text-blue-600 capitalize">{currentStatus}</p>
              </div>
              <div className="bg-green-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">Events Logged</p>
                <p className="text-lg font-semibold text-green-600">{eventLog.length}</p>
              </div>
            </div>
          </div>
        )}

        {/* Waiting for User Input */}
        {waitingForInput && (
          <div className="bg-yellow-50 border-2 border-yellow-200 rounded-lg p-6 mb-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Bot Needs Your Input</h2>
            <div className="bg-white p-4 rounded-lg mb-4">
              <p className="text-gray-700 font-medium">{currentQuestion?.text || 'Please provide information'}</p>
            </div>

            {/* Multiple Choice */}
            {currentQuestion?.options && currentQuestion.options.length > 0 ? (
              <div className="mb-4">
                <div className="space-y-2">
                  {currentQuestion.options.map((option, index) => (
                    <label key={index} className="flex items-center p-3 border border-gray-300 rounded-lg cursor-pointer hover:bg-gray-50">
                      <input
                        type="radio"
                        name="options"
                        value={option}
                        checked={userAnswer === option}
                        onChange={(e) => setUserAnswer(e.target.value)}
                        className="mr-3"
                      />
                      <span className="text-gray-700">{option}</span>
                    </label>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mb-4">
                <input
                  value={userAnswer}
                  onChange={(e) => setUserAnswer(e.target.value)}
                  type="text"
                  placeholder="Type your answer..."
                  onKeyUp={(e) => e.key === 'Enter' && submitAnswer()}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-500"
                />
              </div>
            )}

            <button
              onClick={submitAnswer}
              disabled={!userAnswer}
              className="w-full px-4 py-3 bg-yellow-600 text-white rounded-lg font-semibold hover:bg-yellow-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition"
            >
              Submit Answer
            </button>
          </div>
        )}

        {/* Event Log */}
        {eventLog.length > 0 && (
          <div className="bg-white rounded-lg shadow-md p-6 mb-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Event Log ({eventLog.length})</h2>
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {eventLog.map((event, index) => (
                <div key={index} className={`p-3 rounded-lg ${getEventColorClass(event.type)}`}>
                  <div className="flex justify-between items-start">
                    <div>
                      <p className={`font-semibold ${getEventTextColor(event.type)}`}>{event.type}</p>
                      {event.details && <p className="text-sm text-gray-600 mt-1">{event.details}</p>}
                    </div>
                    <span className="text-xs text-gray-500">{formatTime(event.timestamp)}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Completion Message */}
        {isCompleted && (
          <div className="bg-green-50 border-2 border-green-200 rounded-lg p-6 mb-8">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-3xl">✓</span>
              <h2 className="text-lg font-semibold text-green-800">Application Completed!</h2>
            </div>
            <p className="text-green-700">The job application has been successfully submitted.</p>
          </div>
        )}

        {/* Error Message */}
        {errorMessage && (
          <div className="bg-red-50 border-2 border-red-200 rounded-lg p-6 mb-8">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-3xl">✕</span>
              <h2 className="text-lg font-semibold text-red-800">Application Error</h2>
            </div>
            <p className="text-red-700">{errorMessage}</p>
          </div>
        )}
      </div>
    </div>
  );
};
