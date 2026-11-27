import { useCallback, useEffect, useRef, useState } from 'react';

export type MicErrorKind =
  | 'unsupported'
  | 'permission_denied'
  | 'no_speech'
  | 'audio_capture'
  | 'network'
  | 'recognition_failed'
  | null;

interface SpeechRecognitionAlternativeLike {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
}

interface SpeechRecognitionErrorEventLike extends Event {
  error: string;
  message?: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  }
}

export function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

export interface PlaybackCallbacks {
  onStart?: () => void;
  onEnd?: () => void;
}

export function speakReadback(
  text: string,
  enabled: boolean,
  callbacks?: PlaybackCallbacks,
): void {
  if (!enabled || !text.trim() || typeof window === 'undefined') {
    callbacks?.onEnd?.();
    return;
  }
  if (!('speechSynthesis' in window)) {
    callbacks?.onEnd?.();
    return;
  }

  callbacks?.onStart?.();
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  const voices = window.speechSynthesis.getVoices();
  const indianVoice =
    voices.find((v) => v.lang.toLowerCase().startsWith('hi-in')) ??
    voices.find((v) => v.lang.toLowerCase().startsWith('en-in'));
  if (indianVoice) {
    utterance.voice = indianVoice;
    utterance.lang = indianVoice.lang;
  } else {
    utterance.lang = 'hi-IN';
  }
  utterance.rate = 0.96;

  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    window.setTimeout(() => {
      callbacks?.onEnd?.();
    }, 280);
  };

  utterance.onend = finish;
  utterance.onerror = finish;
  window.setTimeout(finish, 9000);
  window.speechSynthesis.speak(utterance);
}

interface UseSpeechRecognitionOptions {
  lang: string;
  onFinalTranscript: (transcript: string) => void;
}

export function useSpeechRecognition({
  lang,
  onFinalTranscript,
}: UseSpeechRecognitionOptions) {
  const ctor = getSpeechRecognitionCtor();
  const isSupported = ctor !== null;

  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [sessionActive, setSessionActive] = useState(false);
  const [interimText, setInterimText] = useState('');
  const [failureCount, setFailureCount] = useState(0);
  const [errorKind, setErrorKind] = useState<MicErrorKind>(
    isSupported ? null : 'unsupported',
  );
  const [errorMessage, setErrorMessage] = useState<string>(
    isSupported
      ? ''
      : 'Browser speech recognition is not supported here. Use Chrome/Edge or the transcript input below.',
  );

  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const voiceSessionActiveRef = useRef(false);
  const isSpeakingRef = useRef(false);
  const noSpeechCountRef = useRef(0);
  const onFinalRef = useRef(onFinalTranscript);
  onFinalRef.current = onFinalTranscript;

  const endSession = useCallback(() => {
    voiceSessionActiveRef.current = false;
    setSessionActive(false);
    noSpeechCountRef.current = 0;
    if (recognitionRef.current) {
      const recognition = recognitionRef.current;
      recognitionRef.current = null;
      try {
        recognition.abort();
      } catch {
        // Ignore stop errors
      }
    }
    setIsListening(false);
  }, []);

  const stopListening = useCallback(() => {
    endSession();
  }, [endSession]);

  const pauseForPlayback = useCallback(() => {
    isSpeakingRef.current = true;
    setIsSpeaking(true);
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        // Ignore abort errors
      }
    }
    setIsListening(false);
    setInterimText('');
  }, []);

  const clearError = useCallback(() => {
    if (isSupported) {
      setErrorKind(null);
      setErrorMessage('');
    }
  }, [isSupported]);

  const startRecognitionInstance = useCallback(() => {
    if (isSpeakingRef.current) return;

    const Recognition = getSpeechRecognitionCtor();
    if (!Recognition) {
      setErrorKind('unsupported');
      setErrorMessage(
        'Browser speech recognition is not supported in this browser. Use the transcript input below.',
      );
      return;
    }

    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {
        // Ignore cleanup errors
      }
    }

    const recognition = new Recognition();
    recognition.lang = lang;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    let deliveredFinal = false;
    recognition.onstart = () => {
      if (recognitionRef.current !== recognition || !voiceSessionActiveRef.current) return;
      setIsListening(true);
      setInterimText('');
      setErrorKind(null);
      setErrorMessage('');
    };

    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      if (recognitionRef.current !== recognition || !voiceSessionActiveRef.current || isSpeakingRef.current || deliveredFinal) return;
      noSpeechCountRef.current = 0;
      let interim = '';
      let finalChunk = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const text = result[0]?.transcript ?? '';
        if (result.isFinal) {
          finalChunk += text;
        } else {
          interim += text;
        }
      }
      if (interim) {
        setInterimText(interim.trim());
      }
      const cleaned = finalChunk.trim();
      if (cleaned) {
        deliveredFinal = true;
        setFailureCount(0);
        setInterimText('');
        onFinalRef.current(cleaned);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEventLike) => {
      if (recognitionRef.current !== recognition || !voiceSessionActiveRef.current || isSpeakingRef.current) return;
      setIsListening(false);
      setInterimText('');
      if (event.error === 'aborted') {
        return;
      }
      setFailureCount((c) => c + 1);
      switch (event.error) {
        case 'not-allowed':
        case 'service-not-allowed':
          endSession();
          setErrorKind('permission_denied');
          setErrorMessage(
            'Microphone permission was denied. Allow mic access in browser site settings or use the typed fallback below.',
          );
          break;
        case 'no-speech':
          noSpeechCountRef.current += 1;
          if (noSpeechCountRef.current >= 2) {
            endSession();
            setErrorKind('no_speech');
            setErrorMessage(
              'Stopped listening after inactivity. Tap the microphone again or use the typed fallback below.',
            );
          } else if (voiceSessionActiveRef.current && !isSpeakingRef.current) {
            // Brief retry once before timing out
            window.setTimeout(() => {
              if (voiceSessionActiveRef.current && !isSpeakingRef.current) {
                startRecognitionInstance();
              }
            }, 300);
          }
          break;
        case 'audio-capture':
          endSession();
          setErrorKind('audio_capture');
          setErrorMessage(
            'No working microphone was found. Check your mic connection or use the typed fallback below.',
          );
          break;
        case 'network':
          endSession();
          setErrorKind('network');
          setErrorMessage(
            'Speech recognition network error. Check connectivity or use the typed fallback below.',
          );
          break;
        default:
          endSession();
          setErrorKind('recognition_failed');
          setErrorMessage(
            `Speech recognition failed (${event.error}). Try again or use the typed fallback below.`,
          );
      }
    };

    recognition.onend = () => {
      if (recognitionRef.current === recognition) setIsListening(false);
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      setIsListening(false);
      setErrorKind('recognition_failed');
      setErrorMessage(
        'Could not start microphone recognition. Try again or use the typed fallback below.',
      );
    }
  }, [endSession, lang]);

  const startListening = useCallback(() => {
    voiceSessionActiveRef.current = true;
    setSessionActive(true);
    noSpeechCountRef.current = 0;
    if (!isSpeakingRef.current) {
      startRecognitionInstance();
    }
  }, [startRecognitionInstance]);

  const finishPlayback = useCallback(() => {
    isSpeakingRef.current = false;
    setIsSpeaking(false);
    if (voiceSessionActiveRef.current) {
      startRecognitionInstance();
    }
  }, [startRecognitionInstance]);

  useEffect(() => {
    return () => {
      voiceSessionActiveRef.current = false;
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // Ignore unmount abort errors
        }
      }
    };
  }, []);

  return {
    isSupported,
    isListening,
    isSpeaking,
    sessionActive,
    interimText,
    failureCount,
    suggestManualFallback: !isSupported || failureCount >= 2,
    errorKind,
    errorMessage,
    startListening,
    stopListening,
    endSession,
    pauseForPlayback,
    finishPlayback,
    clearError,
  };
}
