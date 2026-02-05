import re
import time
from difflib import SequenceMatcher
from typing import List, Tuple, Optional
from django.db import models
from .models import AIKnowledgeBase, AIConversation, AILearningMetrics

class LocalAIService:
    """Local AI service that learns from conversations and provides intelligent responses"""
    
    def __init__(self):
        self.min_confidence_threshold = 0.6
        self.max_response_time = 2.0  # seconds
    
    def get_response(self, question: str, user_id: str = None, session_id: str = None) -> Tuple[str, float, float]:
        """
        Get AI response based on knowledge base
        Returns: (answer, confidence_score, response_time)
        """
        start_time = time.time()
        
        try:
            # Clean and normalize the question
            normalized_question = self._normalize_text(question)
            
            # Search knowledge base for best match
            best_match = self._find_best_match(normalized_question)
            
            if best_match and best_match[1] >= self.min_confidence_threshold:
                answer = best_match[0].answer
                confidence = best_match[1]
                
                # Update usage count
                best_match[0].usage_count += 1
                best_match[0].save()
            else:
                # Generate a learning response
                answer = self._generate_learning_response(question)
                confidence = 0.3
            
            response_time = time.time() - start_time
            
            # Store conversation for learning
            self._store_conversation(question, answer, user_id, session_id, response_time)
            
            return answer, confidence, response_time
            
        except Exception as e:
            # Fallback response if anything goes wrong
            response_time = time.time() - start_time
            return "I'm having trouble right now, but I'm here to help! Please try again.", 0.1, response_time
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for better matching"""
        # Convert to lowercase
        text = text.lower()
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        return text
    
    def _find_best_match(self, question: str) -> Optional[Tuple[AIKnowledgeBase, float]]:
        """Find the best matching knowledge base entry"""
        try:
            best_match = None
            best_score = 0.0
            
            # Get all knowledge base entries
            entries = AIKnowledgeBase.objects.all()
            
            for entry in entries:
                normalized_entry = self._normalize_text(entry.question)
                
                # Calculate similarity score
                similarity = SequenceMatcher(None, question, normalized_entry).ratio()
                
                # Boost score based on usage count and confidence
                boosted_score = similarity * (1 + entry.usage_count * 0.1) * (1 + entry.confidence_score * 0.2)
                
                if boosted_score > best_score:
                    best_score = boosted_score
                    best_match = (entry, boosted_score)
            
            return best_match
        except Exception:
            return None
    
    def _generate_learning_response(self, question: str) -> str:
        """Generate a professional response when no good match is found"""
        responses = [
            "I don't have specific information about that right now. For detailed assistance, please contact our team at info@eclick.co.za or call +27 76 740 1777.",
            "That's a great question! For personalized answers, I recommend reaching out to our team directly at info@eclick.co.za or +27 76 740 1777.",
            "I'd like to give you the most accurate information. Please contact our team at info@eclick.co.za or call +27 76 740 1777, and they'll be happy to help!",
            "For specific details about that, our team can provide the best assistance. Reach us at info@eclick.co.za or +27 76 740 1777.",
            "I want to make sure you get the right information. Please contact our team at info@eclick.co.za or call +27 76 740 1777 for detailed assistance."
        ]

        # Use question hash to consistently pick response
        import hashlib
        hash_value = int(hashlib.md5(question.encode()).hexdigest(), 16)
        return responses[hash_value % len(responses)]
    
    def _store_conversation(self, question: str, answer: str, user_id: str, session_id: str, response_time: float):
        """Store conversation for learning purposes"""
        try:
            AIConversation.objects.create(
                user_id=user_id or '',
                session_id=session_id or 'anonymous',
                question=question,
                answer=answer,
                response_time=response_time
            )
            
            # Update metrics
            self._update_metrics()
        except Exception:
            # Silently fail if we can't store conversation
            pass
    
    def _update_metrics(self):
        """Update AI learning metrics"""
        try:
            metrics, created = AILearningMetrics.objects.get_or_create(id=1)
            
            # Count total conversations
            metrics.total_conversations = AIConversation.objects.count()
            
            # Count successful responses (confidence > threshold)
            successful = AIConversation.objects.filter(
                response_time__lte=self.max_response_time
            ).count()
            metrics.successful_responses = successful
            
            # Calculate average response time
            avg_time = AIConversation.objects.aggregate(
                avg_time=models.Avg('response_time')
            )['avg_time'] or 0.0
            metrics.average_response_time = avg_time
            
            # Knowledge base size
            metrics.knowledge_base_size = AIKnowledgeBase.objects.count()
            
            metrics.save()
        except Exception:
            # Silently fail if we can't update metrics
            pass
    
    def learn_from_feedback(self, conversation_id: int, was_helpful: bool):
        """Learn from user feedback"""
        try:
            conversation = AIConversation.objects.get(id=conversation_id)
            conversation.was_helpful = was_helpful
            conversation.save()
            
            # If helpful, boost confidence of similar knowledge entries
            if was_helpful:
                self._boost_confidence(conversation.question)
            
        except AIConversation.DoesNotExist:
            pass
    
    def _boost_confidence(self, question: str):
        """Boost confidence of knowledge base entries based on helpful feedback"""
        try:
            normalized_question = self._normalize_text(question)
            
            for entry in AIKnowledgeBase.objects.all():
                normalized_entry = self._normalize_text(entry.question)
                similarity = SequenceMatcher(None, normalized_question, normalized_entry).ratio()
                
                if similarity > 0.7:  # High similarity
                    entry.confidence_score = min(1.0, entry.confidence_score + 0.1)
                    entry.save()
        except Exception:
            pass
    
    def add_knowledge(self, question: str, answer: str, category: str = "", tags: List[str] = None):
        """Add new knowledge to the base"""
        try:
            # Check if similar question already exists
            normalized_question = self._normalize_text(question)
            existing = self._find_best_match(normalized_question)
            
            if existing and existing[1] > 0.8:
                # Update existing entry
                entry = existing[0]
                entry.answer = answer
                entry.confidence_score = min(1.0, entry.confidence_score + 0.1)
                entry.usage_count += 1
                if category:
                    entry.category = category
                if tags:
                    entry.tags = tags
                entry.save()
            else:
                # Create new entry
                AIKnowledgeBase.objects.create(
                    question=question,
                    answer=answer,
                    confidence_score=0.7,  # Start with good confidence
                    category=category,
                    tags=tags or []
                )
        except Exception:
            # Silently fail if we can't add knowledge
            pass
    
    def get_learning_stats(self) -> dict:
        """Get AI learning statistics"""
        try:
            metrics = AILearningMetrics.objects.get(id=1)
            return {
                'total_conversations': metrics.total_conversations,
                'successful_responses': metrics.successful_responses,
                'success_rate': (metrics.successful_responses / metrics.total_conversations * 100) if metrics.total_conversations > 0 else 0,
                'average_response_time': round(metrics.average_response_time, 2),
                'knowledge_base_size': metrics.knowledge_base_size,
                'last_updated': metrics.last_updated
            }
        except AILearningMetrics.DoesNotExist:
            return {
                'total_conversations': 0,
                'successful_responses': 0,
                'success_rate': 0,
                'average_response_time': 0,
                'knowledge_base_size': 0,
                'last_updated': None
            }
    
    def initialize_knowledge_base(self):
        """Initialize with some basic knowledge"""
        try:
            basic_knowledge = [
                {
                    'question': 'What services do you offer?',
                    'answer': 'We offer custom web development, mobile apps, cloud solutions, and AI consulting. How can I help you with your project?',
                    'category': 'services',
                    'tags': ['services', 'web development', 'mobile apps']
                },
                {
                    'question': 'How can I contact you?',
                    'answer': 'You can reach us through our contact form, email at info@eclick.co.za, or by phone. I\'m here to help answer any questions!',
                    'category': 'contact',
                    'tags': ['contact', 'email', 'phone']
                },
                {
                    'question': 'What is E-Click?',
                    'answer': 'E-Click is a software development company specializing in custom solutions. We help businesses transform their ideas into powerful digital experiences.',
                    'category': 'company',
                    'tags': ['company', 'about', 'software development']
                }
            ]
            
            for item in basic_knowledge:
                self.add_knowledge(
                    question=item['question'],
                    answer=item['answer'],
                    category=item['category'],
                    tags=item['tags']
                )
        except Exception:
            pass

# Global AI service instance
ai_service = LocalAIService()
