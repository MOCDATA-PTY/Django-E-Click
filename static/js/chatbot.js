// Chatbot JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initChatbot();
});

function initChatbot() {
    const chatbotButton = document.getElementById('chatbot-button');
    const chatbotWindow = document.getElementById('chatbot-window');
    const chatbotClose = document.getElementById('chatbot-close');
    const chatbotForm = document.getElementById('chatbot-form');
    const chatbotInput = document.getElementById('chatbot-input');
    const chatbotMessages = document.getElementById('chatbot-messages');
    const initialTimestamp = document.getElementById('initial-timestamp');
    
    if (!chatbotButton || !chatbotWindow) return;
    
    let isOpen = false;
    let messages = [];
    
    // Bot response patterns
    const botResponses = {
        service: [
            "E-click offers custom software development, cloud solutions, business automation, enterprise integration, and technical consultancy services.",
            "Our services include tailored software solutions, cloud infrastructure, process automation, system integration, and expert technical advice."
        ],
        automation: [
            "Our automation services help businesses streamline workflows, reduce manual tasks, and increase efficiency through intelligent process automation.",
            "We create custom automation solutions that digitize your business processes, saving time and reducing human error."
        ],
        price: [
            "Our pricing varies based on project requirements. We'd be happy to provide a custom quote - please contact our team at contact@eclick.com.",
            "We offer competitive pricing tailored to your specific needs. Reach out through our contact form for a detailed estimate."
        ],
        contact: [
            "You can reach us through the contact form on our website, by email at contact@eclick.com, or by phone at (555) 123-4567.",
            "Our team is available Monday to Friday, 9am-5pm. Feel free to use the contact section on this website!"
        ],
        default: [
            "I don't have that information right now. Would you like to speak with a member of our team?",
            "Great question! For more detailed information, I recommend reaching out to our team through the contact form.",
            "I'm a simple bot with limited knowledge. For more specific assistance, please contact our human team."
        ]
    };
    
    // Keywords for matching user queries (removed theme keywords)
    const keywords = {
        service: ['service', 'offer', 'provide'],
        automation: ['automat', 'workflow', 'process'],
        price: ['price', 'cost', 'much'],
        contact: ['contact', 'reach', 'talk']
    };
    
    // Initialize timestamp
    if (initialTimestamp) {
        initialTimestamp.textContent = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    }
    
    // Toggle chatbot
    function toggleChatbot() {
        isOpen = !isOpen;
        
        if (isOpen) {
            chatbotWindow.classList.remove('opacity-0', 'scale-95', 'pointer-events-none');
            chatbotWindow.classList.add('opacity-100', 'scale-100');
            chatbotButton.classList.remove('scale-100');
            chatbotButton.classList.add('scale-0');
            
            // Focus input
            setTimeout(() => {
                if (chatbotInput) chatbotInput.focus();
            }, 300);
        } else {
            chatbotWindow.classList.add('opacity-0', 'scale-95', 'pointer-events-none');
            chatbotWindow.classList.remove('opacity-100', 'scale-100');
            chatbotButton.classList.remove('scale-0');
            chatbotButton.classList.add('scale-100');
        }
    }
    
    // Add message to chat
    function addMessage(text, isBot = false) {
        const message = {
            text: text,
            isBot: isBot,
            timestamp: new Date()
        };
        
        messages.push(message);
        renderMessage(message);
        scrollToBottom();
    }
    
    // Render a single message
    function renderMessage(message) {
        if (!chatbotMessages) return;
        
        const isDark = document.documentElement.classList.contains('dark');
        const messageDiv = document.createElement('div');
        messageDiv.className = `mb-2 flex ${message.isBot ? 'justify-start' : 'justify-end'}`;
        
        const bubbleClass = message.isBot 
            ? (isDark ? 'bg-gray-700 border border-gray-600 text-gray-100' : 'bg-white border border-gray-200 text-gray-800')
            : (isDark ? 'bg-accent text-white' : 'bg-red-600 text-white');
        
        messageDiv.innerHTML = `
            <div class="max-w-[80%] rounded-lg p-2.5 ${bubbleClass}">
                <p class="text-sm leading-snug">${message.text}</p>
                <p class="text-xs mt-0.5 ${isDark ? 'opacity-50' : 'opacity-70'}">
                    ${message.timestamp.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                </p>
            </div>
        `;
        
        chatbotMessages.appendChild(messageDiv);
    }
    
    // Handle theme switching
    function handleThemeInput(input) {
        const normalizedInput = input.toLowerCase().trim();

        if (normalizedInput.includes('dark') ||
            normalizedInput.includes('night') ||
            normalizedInput.includes('dark mode') ||
            normalizedInput.includes('i want dark') ||
            normalizedInput.includes('switch to dark') ||
            normalizedInput.includes('make it dark')) {
          
          // Properly set theme with localStorage
          localStorage.setItem('theme', 'dark');
          if (window.applyTheme) {
              window.applyTheme('dark');
          }
          return 'Switching to dark mode! 🌙 Enjoy the darker interface.';
        }

        if (normalizedInput.includes('light') ||
            normalizedInput.includes('day') ||
            normalizedInput.includes('light mode') ||
            normalizedInput.includes('i want light') ||
            normalizedInput.includes('switch to light') ||
            normalizedInput.includes('make it light')) {
          
          // Properly set theme with localStorage  
          localStorage.setItem('theme', 'light');
          if (window.applyTheme) {
              window.applyTheme('light');
          }
          return 'Switching to light mode! ☀️ Enjoy the brighter interface.';
        }

        return null; // No theme change requested
    }
    
    // Generate bot response
    function generateBotResponse(query) {
        // First check if it's a theme request
        const themeResponse = handleThemeInput(query);
        if (themeResponse) {
            return themeResponse;
        }
        
        // Otherwise, use regular keyword matching
        const lowercaseQuery = query.toLowerCase();
        let responseType = 'default';
        
        // Check for keywords
        for (const [category, words] of Object.entries(keywords)) {
            if (words.some(word => lowercaseQuery.includes(word))) {
                responseType = category;
                break;
            }
        }
        
        // Get random response from category
        const responses = botResponses[responseType] || botResponses.default;
        const randomIndex = Math.floor(Math.random() * responses.length);
        return responses[randomIndex];
    }
    
    // Scroll to bottom
    function scrollToBottom() {
        if (chatbotMessages) {
            setTimeout(() => {
                chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
            }, 100);
        }
    }
    
    // Show typing indicator
    function showTypingIndicator() {
        if (!chatbotMessages) return;
        
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'flex justify-start mb-4';
        
        const isDark = document.documentElement.classList.contains('dark');
        const bgClass = isDark ? 'bg-gray-700 border border-gray-600' : 'bg-white border border-gray-200';
        const dotClass = isDark ? 'bg-gray-500' : 'bg-gray-300';
        
        typingDiv.innerHTML = `
            <div class="${bgClass} rounded-lg p-3">
                <div class="flex space-x-2">
                    <div class="w-2 h-2 rounded-full ${dotClass} animate-bounce" style="animation-delay: 0ms"></div>
                    <div class="w-2 h-2 rounded-full ${dotClass} animate-bounce" style="animation-delay: 150ms"></div>
                    <div class="w-2 h-2 rounded-full ${dotClass} animate-bounce" style="animation-delay: 300ms"></div>
                </div>
            </div>
        `;
        
        chatbotMessages.appendChild(typingDiv);
        scrollToBottom();
    }
    
    // Hide typing indicator
    function hideTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }
    
    // Handle form submission
    function handleSubmit(e) {
        e.preventDefault();
        
        const userInput = chatbotInput.value.trim();
        if (!userInput) return;
        
        // Add user message
        addMessage(userInput, false);
        chatbotInput.value = '';
        
        // Show typing indicator
        showTypingIndicator();
        
        // Generate and show bot response after delay
        setTimeout(() => {
            hideTypingIndicator();
            const botResponse = generateBotResponse(userInput);
            addMessage(botResponse, true);
        }, 1000 + Math.random() * 1000);
    }
    
    // Update input state
    function updateInputState() {
        const submitButton = chatbotForm?.querySelector('button[type="submit"]');
        if (submitButton && chatbotInput) {
            submitButton.disabled = !chatbotInput.value.trim();
        }
    }
    
    // Bind event listeners
    if (chatbotButton) {
        chatbotButton.addEventListener('click', toggleChatbot);
    }
    
    if (chatbotClose) {
        chatbotClose.addEventListener('click', toggleChatbot);
    }
    
    if (chatbotForm) {
        chatbotForm.addEventListener('submit', handleSubmit);
    }
    
    if (chatbotInput) {
        chatbotInput.addEventListener('input', updateInputState);
        chatbotInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
            }
        });
    }
    
    // Close chatbot when clicking outside
    document.addEventListener('click', (e) => {
        if (isOpen && !chatbotWindow.contains(e.target) && !chatbotButton.contains(e.target)) {
            toggleChatbot();
        }
    });
    
    // Initialize input state
    updateInputState();
}