import React, { useState, useRef, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { MessageSquare, Sparkles } from 'lucide-react';
import { chatApi } from '../lib/api';
import type { ChatQueryRequest, ChatQueryResponse } from '../lib/api';
import { MessageBubble } from './MessageBubble';
import { TypingIndicator } from './TypingIndicator';
import { InputBar } from './InputBar';
import { generateSessionId } from '../lib/utils';

interface Message {
  id: string;
  content: string;
  type: 'user' | 'assistant';
  sources?: ChatQueryResponse['sources'];
  timestamp: Date;
}

interface ChatInterfaceProps {
  payerFilter?: string;
  ruleTypeFilter?: string;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  payerFilter,
  ruleTypeFilter,
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId] = useState(() => generateSessionId());
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const chatMutation = useMutation({
    mutationFn: (query: string) => {
      const request: ChatQueryRequest = {
        query,
        session_id: sessionId,
        payer_name: payerFilter || undefined,
        rule_type: ruleTypeFilter || undefined,
        include_sources: true,
      };
      return chatApi.query(request);
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          content: data.response,
          type: 'assistant',
          sources: data.sources,
          timestamp: new Date(),
        },
      ]);
    },
    onError: (error) => {
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          content: 'Sorry, I encountered an error. Please try again.',
          type: 'assistant',
          timestamp: new Date(),
        },
      ]);
      console.error('Chat error:', error);
    },
  });

  const handleSend = (message: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        content: message,
        type: 'user',
        timestamp: new Date(),
      },
    ]);
    chatMutation.mutate(message);
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 shadow-sm">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-lg">
              <MessageSquare className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">
                Healthcare Payer Knowledge Base
              </h1>
              <p className="text-sm text-gray-500">
                Ask about payer rules, timely filing, and more
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span>Online</span>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-6 py-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {messages.length === 0 ? (
            <div className="text-center py-12">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary-100 mb-4">
                <Sparkles className="w-8 h-8 text-primary-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                Welcome to Payer Knowledge Base
              </h2>
              <p className="text-gray-600 mb-8 max-w-md mx-auto">
                Ask me anything about healthcare payer rules. I'll provide accurate answers
                with source citations.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl mx-auto">
                {[
                  "What's Aetna's timely filing rule?",
                  "Tell me about prior authorization requirements",
                  "What are United Healthcare's appeals processes?",
                  "Compare timely filing rules across payers",
                ].map((example, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(example)}
                    className="text-left p-4 rounded-lg border border-gray-200 hover:border-primary-300 hover:bg-primary-50 transition-all group"
                  >
                    <p className="text-sm text-gray-700 group-hover:text-primary-700">
                      {example}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              {messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  content={message.content}
                  type={message.type}
                  sources={message.sources}
                  timestamp={message.timestamp}
                />
              ))}
              {chatMutation.isPending && <TypingIndicator />}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <InputBar
        onSend={handleSend}
        isLoading={chatMutation.isPending}
        disabled={false}
      />
    </div>
  );
};
