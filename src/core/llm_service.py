"""
Сервис для работы с большими языковыми моделями.
Поддерживает OpenAI API и локальные модели через Ollama.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import os

# Для работы с OpenAI
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Для работы с локальными моделями
try:
    import ollama
except ImportError:
    ollama = None


@dataclass
class LLMResponse:
    """Структура ответа от LLM."""
    content: str
    model: str
    tokens_used: int
    finish_reason: str


class BaseLLMProvider(ABC):
    """Абстрактный базовый класс для провайдеров LLM."""
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> LLMResponse:
        """Генерация текста на основе промпта."""
        pass
    
    @abstractmethod
    def generate_with_context(
        self,
        prompt: str,
        context: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Генерация с учётом контекста (для RAG)."""
        pass


class OpenAIProvider(BaseLLMProvider):
    """Провайдер для OpenAI API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o"
    ):
        if OpenAI is None:
            raise ImportError("Установите openai: pip install openai")
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("API ключ OpenAI не найден")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = model
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> LLMResponse:
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=self.model,
            tokens_used=response.usage.total_tokens,
            finish_reason=response.choices[0].finish_reason
        )
    
    def generate_with_context(
        self,
        prompt: str,
        context: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        # Формируем контекст из документов
        context_text = "\n\n".join([
            f"Документ {i+1}:\n{doc['content']}"
            for i, doc in enumerate(context)
        ])
        
        enhanced_prompt = f"""Контекст:
{context_text}

Вопрос/Задача: {prompt}

Используй информацию из контекста для ответа."""
        
        return self.generate(
            prompt=enhanced_prompt,
            system_prompt=system_prompt
        )


class OllamaProvider(BaseLLMProvider):
    """Провайдер для локальных моделей через Ollama."""
    
    def __init__(
        self,
        model: str = "llama3.1:8b",
        host: str = "http://localhost:11434"
    ):
        if ollama is None:
            raise ImportError("Установите ollama: pip install ollama")
        
        self.model = model
        self.host = host
        self.client = ollama.Client(host=host)
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> LLMResponse:
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat(
            model=self.model,
            messages=messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens
            }
        )
        
        return LLMResponse(
            content=response['message']['content'],
            model=self.model,
            tokens_used=response.get('eval_count', 0),
            finish_reason="stop"
        )
    
    def generate_with_context(
        self,
        prompt: str,
        context: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        context_text = "\n\n".join([
            f"Документ {i+1}:\n{doc['content']}"
            for i, doc in enumerate(context)
        ])
        
        enhanced_prompt = f"""Контекст:
{context_text}

Вопрос/Задача: {prompt}"""
        
        return self.generate(
            prompt=enhanced_prompt,
            system_prompt=system_prompt,
            temperature=0.3  # Меньше креативности для RAG
        )


class LLMService:
    """
    Основной сервис для работы с LLM.
    Обеспечивает единый интерфейс для разных провайдеров.
    """
    
    def __init__(self, provider: Optional[BaseLLMProvider] = None):
        self.provider = provider or self._create_default_provider()
    
    def _create_default_provider(self) -> BaseLLMProvider:
        """Создание провайдера по умолчанию."""
        # Пробуем OpenAI
        if os.getenv("OPENAI_API_KEY"):
            return OpenAIProvider()
        
        # Пробуем Ollama
        try:
            if ollama:
                return OllamaProvider()
        except Exception:
            pass
        
        raise ValueError(
            "Не удалось инициализировать LLM провайдер. "
            "Установите OPENAI_API_KEY или запустите Ollama."
        )
    
    def generate_documentation(
        self,
        code: str,
        doc_type: str = "technical"
    ) -> str:
        """Генерация документации для кода."""
        prompts = {
            "technical": """Создай техническую документацию для следующего кода.
Включи:
- Описание назначения
- Параметры и возвращаемые значения
- Примеры использования
- Возможные исключения""",
            
            "user": """Создай пользовательскую документацию для следующего кода.
Включи:
- Простое описание функциональности
- Пошаговую инструкцию использования
- Примеры""",
            
            "api": """Создай API документацию в формате OpenAPI/Swagger.
Включи endpoints, параметры, примеры запросов и ответов."""
        }
        
        system_prompt = prompts.get(doc_type, prompts["technical"])
        
        response = self.provider.generate(
            prompt=f"Код:\n```\n{code}\n```",
            system_prompt=system_prompt,
            temperature=0.3
        )
        
        return response.content
    
    def analyze_requirements(
        self,
        requirements_text: str
    ) -> Dict[str, Any]:
        """Анализ текстовых требований."""
        system_prompt = """Ты эксперт по анализу требований к ПО.
Проанализируй требования и верни JSON с полями:
- functional_requirements: список функциональных требований
- non_functional_requirements: список нефункциональных требований
- ambiguities: неоднозначности и проблемы
- missing_info: недостающая информация
- recommendations: рекомендации по улучшению"""
        
        response = self.provider.generate(
            prompt=f"Требования:\n{requirements_text}",
            system_prompt=system_prompt,
            temperature=0.2
        )
        
        import json
        try:
            # Пытаемся извлечь JSON из ответа
            content = response.content
            start = content.find('{')
            end = content.rfind('}') + 1
            return json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            return {"raw_analysis": response.content}
    
    def generate_test_cases(
        self,
        feature_description: str,
        test_type: str = "functional"
    ) -> List[Dict[str, str]]:
        """Генерация тест-кейсов для функциональности."""
        system_prompt = f"""Создай {test_type} тест-кейсы для описанной функциональности.
Для каждого тест-кейса укажи:
- ID
- Название
- Предусловия
- Шаги
- Ожидаемый результат
- Приоритет

Верни результат в формате JSON массива."""
        
        response = self.provider.generate(
            prompt=feature_description,
            system_prompt=system_prompt,
            temperature=0.4
        )
        
        import json
        try:
            content = response.content
            start = content.find('[')
            end = content.rfind(']') + 1
            return json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            return [{"raw": response.content}]
    
    def generate_release_notes(
        self,
        commits: List[str],
        version: str
    ) -> str:
        """Генерация release notes на основе коммитов."""
        system_prompt = """Создай release notes на основе списка коммитов.
Структура:
1. Краткое описание версии
2. Новые функции (Features)
3. Исправления (Bug Fixes)
4. Улучшения (Improvements)
5. Критические изменения (Breaking Changes)

Используй понятный язык для конечных пользователей."""
        
        commits_text = "\n".join([f"- {c}" for c in commits])
        
        response = self.provider.generate(
            prompt=f"Версия: {version}\n\nКоммиты:\n{commits_text}",
            system_prompt=system_prompt,
            temperature=0.5
        )
        
        return response.content