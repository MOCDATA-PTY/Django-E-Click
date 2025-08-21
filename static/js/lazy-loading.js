// Lazy Loading and FOUC Prevention Script
(function() {
    'use strict';
    
    // Critical CSS for immediate rendering
    const criticalCSS = `
        * { box-sizing: border-box; }
        body { 
            margin: 0; 
            padding: 0; 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #fff;
        }
        .loading-screen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 9999;
            transition: opacity 0.5s ease-out;
        }
        .content-wrapper { opacity: 0; transition: opacity 0.3s ease-in; }
        .content-wrapper.loaded { opacity: 1; }
    `;
    
    // Inject critical CSS immediately
    function injectCriticalCSS() {
        const style = document.createElement('style');
        style.textContent = criticalCSS;
        document.head.appendChild(style);
    }
    
    // Create loading screen
    function createLoadingScreen() {
        const loadingScreen = document.createElement('div');
        loadingScreen.className = 'loading-screen';
        loadingScreen.innerHTML = `
            <div style="text-align: center;">
                <div class="loading-logo">
                    <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="40" cy="40" r="35" stroke="white" stroke-width="3" fill="none"/>
                        <path d="M25 40 L35 50 L55 30" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </div>
                <div class="loading-spinner"></div>
                <div class="loading-text">Loading E-Click...</div>
            </div>
        `;
        document.body.appendChild(loadingScreen);
        document.body.classList.add('loading');
    }
    
    // Load CSS file asynchronously
    function loadCSS(href, callback) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        link.onload = callback;
        link.onerror = callback;
        document.head.appendChild(link);
    }
    
    // Load multiple CSS files
    function loadMultipleCSS(cssFiles, callback) {
        let loadedCount = 0;
        const totalFiles = cssFiles.length;
        
        if (totalFiles === 0) {
            callback();
            return;
        }
        
        cssFiles.forEach(file => {
            loadCSS(file, () => {
                loadedCount++;
                if (loadedCount === totalFiles) {
                    callback();
                }
            });
        });
    }
    
    // Preload critical resources
    function preloadResources() {
        const resources = [
            // Fonts
            'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap',
            // Icons
            'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
            // Local CSS
            '/static/css/main.css'
        ];
        
        return new Promise((resolve) => {
            loadMultipleCSS(resources, resolve);
        });
    }
    
    // Initialize lazy loading
    function initLazyLoading() {
        // Inject critical CSS immediately
        injectCriticalCSS();
        
        // Create loading screen
        createLoadingScreen();
        
        // Wrap content
        const content = document.body.children;
        const contentWrapper = document.createElement('div');
        contentWrapper.className = 'content-wrapper';
        
        // Move all content except loading screen to wrapper
        Array.from(content).forEach(child => {
            if (!child.classList.contains('loading-screen')) {
                contentWrapper.appendChild(child);
            }
        });
        
        document.body.appendChild(contentWrapper);
        
        // Preload resources
        preloadResources().then(() => {
            // Hide loading screen
            const loadingScreen = document.querySelector('.loading-screen');
            if (loadingScreen) {
                loadingScreen.classList.add('fade-out');
                setTimeout(() => {
                    loadingScreen.classList.add('hidden');
                    document.body.classList.remove('loading');
                }, 500);
            }
            
            // Show content
            contentWrapper.classList.add('loaded');
        });
    }
    
    // Lazy load images
    function initImageLazyLoading() {
        const images = document.querySelectorAll('img[data-src]');
        
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                    observer.unobserve(img);
                }
            });
        });
        
        images.forEach(img => imageObserver.observe(img));
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLazyLoading);
    } else {
        initLazyLoading();
    }
    
    // Initialize image lazy loading after content is loaded
    window.addEventListener('load', initImageLazyLoading);
    
    // Export functions for global use
    window.LazyLoader = {
        initLazyLoading,
        initImageLazyLoading,
        loadCSS,
        preloadResources
    };
    
})();
