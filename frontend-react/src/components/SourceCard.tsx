import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Calendar, FileText, ExternalLink } from 'lucide-react';
import type { Source } from '../lib/api';
import { cn, formatDate } from '../lib/utils';

interface SourceCardProps {
  source: Source;
  index: number;
}

export const SourceCard: React.FC<SourceCardProps> = ({ source, index }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  const matchScore = Math.round((source.combined_score || source.similarity_score || 0) * 100);
  
  return (
    <div className="bg-gray-50 rounded-lg border border-gray-200 overflow-hidden transition-all hover:shadow-md">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-xs font-semibold">
            {index + 1}
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-medium text-gray-900 truncate">
              {source.payer_name}
            </div>
            <div className="text-sm text-gray-500 truncate">
              {source.rule_type.replace(/_/g, ' ')}
            </div>
          </div>
          <div className="flex-shrink-0 flex items-center gap-2">
            <span className={cn(
              'text-xs font-medium px-2 py-1 rounded-full',
              matchScore >= 80 ? 'bg-green-100 text-green-700' :
              matchScore >= 60 ? 'bg-yellow-100 text-yellow-700' :
              'bg-gray-100 text-gray-700'
            )}>
              {matchScore}% match
            </span>
            {isExpanded ? (
              <ChevronUp className="w-4 h-4 text-gray-400" />
            ) : (
              <ChevronDown className="w-4 h-4 text-gray-400" />
            )}
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="px-4 pb-4 space-y-3 animate-fade-in">
          {source.title && (
            <div>
              <div className="flex items-center gap-2 text-xs font-medium text-gray-500 mb-1">
                <FileText className="w-3 h-3" />
                Title
              </div>
              <div className="text-sm text-gray-900">{source.title}</div>
            </div>
          )}

          {source.content_excerpt && (
            <div>
              <div className="text-xs font-medium text-gray-500 mb-1">Excerpt</div>
              <div className="text-sm text-gray-700 bg-white p-3 rounded border border-gray-200">
                {source.content_excerpt}
              </div>
            </div>
          )}

          {source.effective_date && (
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <Calendar className="w-4 h-4" />
              <span>Effective: {formatDate(source.effective_date)}</span>
            </div>
          )}

          {source.source_url && (
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-sm text-primary-600 hover:text-primary-700 font-medium transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
              View Source
            </a>
          )}
        </div>
      )}
    </div>
  );
};
