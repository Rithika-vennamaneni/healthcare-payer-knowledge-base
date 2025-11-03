import React from 'react';
import ReactMarkdown from 'react-markdown';
import { User, Bot, ExternalLink } from 'lucide-react';
import type { Source } from '../lib/api';
import { cn, formatDate } from '../lib/utils';
import { SourceCard } from './SourceCard';

interface MessageBubbleProps {
  content: string;
  type: 'user' | 'assistant';
  sources?: Source[];
  timestamp?: Date;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  content,
  type,
  sources,
  timestamp,
}) => {
  const isUser = type === 'user';

  return (
    <div
      className={cn(
        'flex gap-3 chat-message',
        isUser ? 'justify-end' : 'justify-start'
      )}
    >
      {!isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-500 flex items-center justify-center">
          <Bot className="w-5 h-5 text-white" />
        </div>
      )}

      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-4 py-3 shadow-sm',
          isUser
            ? 'bg-primary-500 text-white rounded-br-sm'
            : 'bg-white border border-gray-200 rounded-bl-sm'
        )}
      >
        <div className={cn('prose prose-sm max-w-none', isUser && 'prose-invert')}>
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              ul: ({ children }) => <ul className="mb-2 last:mb-0 ml-4">{children}</ul>,
              ol: ({ children }) => <ol className="mb-2 last:mb-0 ml-4">{children}</ol>,
              li: ({ children }) => <li className="mb-1">{children}</li>,
              code: ({ children, className }) => {
                const isInline = !className;
                return isInline ? (
                  <code className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-800 text-sm font-mono">
                    {children}
                  </code>
                ) : (
                  <code className="block p-3 rounded bg-gray-100 text-gray-800 text-sm font-mono overflow-x-auto">
                    {children}
                  </code>
                );
              },
            }}
          >
            {content}
          </ReactMarkdown>
        </div>

        {timestamp && (
          <div className={cn('text-xs mt-2', isUser ? 'text-primary-100' : 'text-gray-400')}>
            {formatDate(timestamp)}
          </div>
        )}

        {sources && sources.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-200">
            <div className="flex items-center gap-2 mb-3">
              <ExternalLink className="w-4 h-4 text-gray-500" />
              <h4 className="text-sm font-semibold text-gray-700">
                Sources ({sources.length})
              </h4>
            </div>
            <div className="space-y-2">
              {sources.map((source, index) => (
                <SourceCard key={source.rule_id || index} source={source} index={index} />
              ))}
            </div>
          </div>
        )}
      </div>

      {isUser && (
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center">
          <User className="w-5 h-5 text-gray-600" />
        </div>
      )}
    </div>
  );
};
