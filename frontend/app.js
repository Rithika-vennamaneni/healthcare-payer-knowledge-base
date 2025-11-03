// API Configuration
const API_BASE_URL = 'http://localhost:8000';

// State Management
let sessionId = null;
let currentPayers = [];

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
    setupEventListeners();
});

async function initializeApp() {
    try {
        // Check API health
        await checkHealth();
        
        // Load initial data
        await Promise.all([
            loadStats(),
            loadPayers(),
            loadAlerts()
        ]);
        
        // Generate session ID
        sessionId = generateSessionId();
        
    } catch (error) {
        console.error('Initialization error:', error);
        showError('Failed to connect to the API. Make sure the server is running.');
    }
}

function setupEventListeners() {
    const sendButton = document.getElementById('sendButton');
    const chatInput = document.getElementById('chatInput');
    const clearButton = document.getElementById('clearChat');
    
    // Send message
    sendButton.addEventListener('click', sendMessage);
    
    // Enter to send (Shift+Enter for new line)
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Auto-resize textarea
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = chatInput.scrollHeight + 'px';
    });
    
    // Clear chat
    clearButton.addEventListener('click', clearChat);
}

// API Functions
async function checkHealth() {
    const response = await fetch(`${API_BASE_URL}/health`);
    const data = await response.json();
    
    const statusIndicator = document.getElementById('statusIndicator');
    const statusDot = statusIndicator.querySelector('.status-dot');
    const statusText = statusIndicator.querySelector('.status-text');
    
    if (data.status === 'healthy') {
        statusDot.classList.add('connected');
        statusText.textContent = 'Connected';
    } else {
        statusText.textContent = 'Disconnected';
    }
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE_URL}/stats`);
        const data = await response.json();
        
        const statsGrid = document.getElementById('statsGrid');
        statsGrid.innerHTML = `
            <div class="stat-card">
                <div class="stat-value">${data.total_payers}</div>
                <div class="stat-label">Total Payers</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${data.total_rules}</div>
                <div class="stat-label">Total Rules</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${data.unread_alerts}</div>
                <div class="stat-label">Unread Alerts</div>
            </div>
        `;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

async function loadPayers() {
    try {
        const response = await fetch(`${API_BASE_URL}/payers`);
        const payers = await response.json();
        currentPayers = payers;
        
        const payersList = document.getElementById('payersList');
        const payerFilter = document.getElementById('payerFilter');
        
        if (payers.length === 0) {
            payersList.innerHTML = '<div class="loading">No payers found</div>';
            return;
        }
        
        // Update sidebar list
        payersList.innerHTML = payers.map(payer => `
            <div class="payer-item" onclick="filterByPayer('${payer.name}')">
                <div class="payer-name">${payer.name}</div>
                <div class="payer-rules">${payer.total_rules} rules</div>
            </div>
        `).join('');
        
        // Update filter dropdown
        payerFilter.innerHTML = '<option value="">All Payers</option>' +
            payers.map(payer => `<option value="${payer.name}">${payer.name}</option>`).join('');
            
    } catch (error) {
        console.error('Error loading payers:', error);
        document.getElementById('payersList').innerHTML = '<div class="loading">Error loading payers</div>';
    }
}

async function loadAlerts() {
    try {
        const response = await fetch(`${API_BASE_URL}/alerts?unread_only=true&limit=5`);
        const alerts = await response.json();
        
        const alertsList = document.getElementById('alertsList');
        
        if (alerts.length === 0) {
            alertsList.innerHTML = '<div class="loading">No new alerts</div>';
            return;
        }
        
        alertsList.innerHTML = alerts.map(alert => `
            <div class="alert-item ${alert.severity}">
                <div class="alert-title">${alert.title}</div>
                <div class="alert-message">${alert.message}</div>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Error loading alerts:', error);
        document.getElementById('alertsList').innerHTML = '<div class="loading">Error loading alerts</div>';
    }
}

// Chat Functions
async function sendMessage() {
    const input = document.getElementById('chatInput');
    const query = input.value.trim();
    
    if (!query) return;
    
    const payerFilter = document.getElementById('payerFilter').value;
    const ruleTypeFilter = document.getElementById('ruleTypeFilter').value;
    
    // Clear input
    input.value = '';
    input.style.height = 'auto';
    
    // Add user message to chat
    addMessage(query, 'user');
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE_URL}/chat/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                query: query,
                session_id: sessionId,
                payer_name: payerFilter || null,
                rule_type: ruleTypeFilter || null,
                include_sources: true
            })
        });
        
        const data = await response.json();
        
        // Remove typing indicator
        removeTypingIndicator();
        
        // Add bot response
        addMessage(data.response, 'bot', data.sources);
        
        // Update session ID
        if (data.session_id) {
            sessionId = data.session_id;
        }
        
    } catch (error) {
        console.error('Error sending message:', error);
        removeTypingIndicator();
        addMessage('Sorry, I encountered an error. Please try again.', 'bot');
    }
}

function addMessage(content, type, sources = null) {
    const messagesContainer = document.getElementById('chatMessages');
    
    // Remove welcome message if it exists
    const welcomeMessage = messagesContainer.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;
    
    let messageHTML = `<div class="message-content">${escapeHtml(content)}`;
    
    // Add sources if available
    if (sources && sources.length > 0) {
        messageHTML += '<div class="message-sources"><h4>📚 Sources:</h4>';
        sources.forEach((source, index) => {
            const score = (source.combined_score || source.similarity_score || 0) * 100;
            messageHTML += `
                <div class="source-item">
                    <span class="source-payer">${index + 1}. ${source.payer_name}</span>
                    <span class="source-score">${score.toFixed(0)}% match</span>
                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
                        ${source.rule_type}
                    </div>
                </div>
            `;
        });
        messageHTML += '</div>';
    }
    
    messageHTML += '</div>';
    messageDiv.innerHTML = messageHTML;
    
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function showTypingIndicator() {
    const messagesContainer = document.getElementById('chatMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message message-bot';
    typingDiv.id = 'typingIndicator';
    typingDiv.innerHTML = `
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    messagesContainer.appendChild(typingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function removeTypingIndicator() {
    const typingIndicator = document.getElementById('typingIndicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

function clearChat() {
    const messagesContainer = document.getElementById('chatMessages');
    messagesContainer.innerHTML = `
        <div class="welcome-message">
            <h3>👋 Welcome!</h3>
            <p>Ask me anything about healthcare payer rules, such as:</p>
            <ul>
                <li>"What is Aetna's timely filing rule?"</li>
                <li>"Tell me about prior authorization requirements"</li>
                <li>"What are the appeals processes for United Healthcare?"</li>
                <li>"Compare timely filing rules across payers"</li>
            </ul>
        </div>
    `;
    sessionId = generateSessionId();
}

function filterByPayer(payerName) {
    const payerFilter = document.getElementById('payerFilter');
    payerFilter.value = payerName;
    
    // Optionally, you could auto-focus the input
    document.getElementById('chatInput').focus();
}

// Utility Functions
function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, '<br>');
}

function showError(message) {
    const statusIndicator = document.getElementById('statusIndicator');
    const statusText = statusIndicator.querySelector('.status-text');
    statusText.textContent = message;
}

// Auto-refresh stats and alerts every 30 seconds
setInterval(() => {
    loadStats();
    loadAlerts();
}, 30000);
