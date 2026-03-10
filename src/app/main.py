"""
Главный модуль приложения.
Предоставляет CLI и Web интерфейсы.
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

# Импорты из других модулей проекта
try:
    from src.core.llm_service import LLMService
    from src.core.rag_engine import RAGEngine, RAGPipeline, Document
    from src.generators.document_generator import (
        DocumentGenerator, DocumentMetadata, DocumentSection,
        DocumentFormat, GOSTSettings
    )
except ImportError:
    # Для запуска как standalone
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from src.core.llm_service import LLMService
    from src.core.rag_engine import RAGEngine, RAGPipeline, Document
    from src.generators.document_generator import (
        DocumentGenerator, DocumentMetadata, DocumentSection,
        DocumentFormat, GOSTSettings
    )


class SDLCAutomationApp:
    """
    Основное приложение для автоматизации текстовых процессов SDLC.
    """
    
    def __init__(
        self,
        llm_provider: str = "auto",
        data_dir: str = "./data"
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Инициализация сервисов
        self.llm_service = None
        self.rag_engine = None
        self.rag_pipeline = None
        self.doc_generator = None
        
        self._initialized = False
        self._llm_provider = llm_provider
    
    def _lazy_init(self):
        """Ленивая инициализация сервисов."""
        if self._initialized:
            return
        
        try:
            self.llm_service = LLMService()
            self.rag_engine = RAGEngine(
                persist_directory=str(self.data_dir / "chromadb")
            )
            self.rag_pipeline = RAGPipeline(self.rag_engine, self.llm_service)
            self.doc_generator = DocumentGenerator(
                llm_service=self.llm_service
            )
            self._initialized = True
        except Exception as e:
            print(f"Предупреждение: не удалось инициализировать LLM сервисы: {e}")
            print("Некоторые функции будут недоступны.")
            self.doc_generator = DocumentGenerator()
            self._initialized = True
    
    def generate_documentation(
        self,
        code_path: str,
        output_path: str,
        doc_type: str = "technical",
        format: str = "docx"
    ) -> Path:
        """
        Генерация документации для кода.
        
        Args:
            code_path: Путь к файлу или директории с кодом
            output_path: Путь для сохранения документации
            doc_type: Тип документации (technical, user, api)
            format: Формат вывода (docx, pdf)
            
        Returns:
            Path: Путь к созданному файлу
        """
        self._lazy_init()
        
        code_path = Path(code_path)
        
        if code_path.is_file():
            code_files = [code_path]
        else:
            # Поддержка разных языков программирования
            extensions = ['*.py', '*.js', '*.ts', '*.java', '*.cpp', '*.c', '*.go']
            code_files = []
            for ext in extensions:
                code_files.extend(code_path.rglob(ext))
        
        if not code_files:
            raise FileNotFoundError(f"Файлы с кодом не найдены в {code_path}")
        
        sections = []
        
        for code_file in code_files:
            print(f"Обработка: {code_file}")
            
            try:
                code_content = code_file.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                code_content = code_file.read_text(encoding='latin-1')
            
            # Генерируем документацию через LLM если доступен
            if self.llm_service:
                doc_content = self.llm_service.generate_documentation(
                    code=code_content,
                    doc_type=doc_type
                )
            else:
                # Базовая документация без LLM
                doc_content = f"Исходный код файла {code_file.name}:\n\n```\n{code_content[:2000]}...\n```"
            
            sections.append(DocumentSection(
                title=f"Модуль {code_file.stem}",
                content=doc_content,
                level=1
            ))
        
        metadata = DocumentMetadata(
            title=f"Техническая документация: {code_path.name}",
            author="SDLC Automation Tool",
            organization="Автоматически сгенерировано"
        )
        
        doc_format = DocumentFormat.DOCX if format.lower() == "docx" else DocumentFormat.PDF
        
        result_path = self.doc_generator.generate(
            metadata=metadata,
            sections=sections,
            format=doc_format,
            output_path=output_path
        )
        
        print(f"Документация создана: {result_path}")
        return result_path
    
    def analyze_requirements(
        self,
        requirements_file: str,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Анализ файла с требованиями.
        
        Args:
            requirements_file: Путь к файлу с требованиями
            output_path: Путь для сохранения отчёта (опционально)
            
        Returns:
            Dict: Результаты анализа
        """
        self._lazy_init()
        
        requirements_path = Path(requirements_file)
        
        if not requirements_path.exists():
            raise FileNotFoundError(f"Файл не найден: {requirements_file}")
        
        requirements_text = requirements_path.read_text(encoding='utf-8')
        
        if not self.llm_service:
            return {"error": "LLM сервис недоступен для анализа требований"}
        
        print("Анализ требований...")
        analysis = self.llm_service.analyze_requirements(requirements_text)
        
        if output_path:
            output_path = Path(output_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)
            print(f"Результаты сохранены: {output_path}")
        
        return analysis
    
    def generate_test_cases(
        self,
        feature_description: str,
        output_path: Optional[str] = None,
        test_type: str = "functional"
    ) -> List[Dict[str, str]]:
        """
        Генерация тест-кейсов для функциональности.
        
        Args:
            feature_description: Описание функциональности
            output_path: Путь для сохранения (опционально)
            test_type: Тип тестов (functional, integration, e2e)
            
        Returns:
            List: Список тест-кейсов
        """
        self._lazy_init()
        
        if not self.llm_service:
            return [{"error": "LLM сервис недоступен"}]
        
        print(f"Генерация {test_type} тест-кейсов...")
        test_cases = self.llm_service.generate_test_cases(
            feature_description=feature_description,
            test_type=test_type
        )
        
        if output_path:
            output_path = Path(output_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(test_cases, f, ensure_ascii=False, indent=2)
            print(f"Тест-кейсы сохранены: {output_path}")
        
        return test_cases
    
    def generate_release_notes(
        self,
        commits_file: str,
        version: str,
        output_path: str,
        format: str = "docx"
    ) -> Path:
        """
        Генерация release notes на основе коммитов.
        
        Args:
            commits_file: Файл со списком коммитов (по одному на строку)
            version: Номер версии
            output_path: Путь для сохранения
            format: Формат вывода (docx, pdf, md)
            
        Returns:
            Path: Путь к созданному файлу
        """
        self._lazy_init()
        
        commits_path = Path(commits_file)
        
        if not commits_path.exists():
            raise FileNotFoundError(f"Файл не найден: {commits_file}")
        
        commits = [
            line.strip() 
            for line in commits_path.read_text(encoding='utf-8').splitlines()
            if line.strip()
        ]
        
        if not self.llm_service:
            release_notes_content = "# Release Notes\n\n" + "\n".join(f"- {c}" for c in commits)
        else:
            print("Генерация release notes...")
            release_notes_content = self.llm_service.generate_release_notes(
                commits=commits,
                version=version
            )
        
        # Если формат markdown - просто сохраняем текст
        if format.lower() == "md":
            output_path = Path(output_path)
            if not output_path.suffix:
                output_path = output_path.with_suffix('.md')
            output_path.write_text(release_notes_content, encoding='utf-8')
            print(f"Release notes сохранены: {output_path}")
            return output_path
        
        # Для DOCX/PDF создаём документ
        sections = [
            DocumentSection(
                title="Release Notes",
                content=release_notes_content,
                level=1
            )
        ]
        
        metadata = DocumentMetadata(
            title=f"Release Notes - Версия {version}",
            author="SDLC Automation Tool",
            version=version
        )
        
        doc_format = DocumentFormat.DOCX if format.lower() == "docx" else DocumentFormat.PDF
        
        result_path = self.doc_generator.generate(
            metadata=metadata,
            sections=sections,
            format=doc_format,
            output_path=output_path
        )
        
        print(f"Release notes созданы: {result_path}")
        return result_path
    
    def create_document(
        self,
        template: str,
        context_file: str,
        output_path: str,
        format: str = "docx"
    ) -> Path:
        """
        Создание документа и�� шаблона.
        
        Args:
            template: Имя шаблона (srs, test_plan, technical_doc, release_notes)
            context_file: JSON файл с данными для заполнения
            output_path: Путь для сохранения
            format: Формат вывода (docx, pdf)
            
        Returns:
            Path: Путь к созданному файлу
        """
        self._lazy_init()
        
        context_path = Path(context_file)
        
        if not context_path.exists():
            raise FileNotFoundError(f"Файл контекста не найден: {context_file}")
        
        with open(context_path, 'r', encoding='utf-8') as f:
            context = json.load(f)
        
        print(f"Создание документа из шаблона '{template}'...")
        
        doc_format = DocumentFormat.DOCX if format.lower() == "docx" else DocumentFormat.PDF
        
        # Получаем метаданные и секции из шаблона
        template_methods = {
            "srs": self.doc_generator._create_srs_template,
            "test_plan": self.doc_generator._create_test_plan_template,
            "technical_doc": self.doc_generator._create_technical_doc_template,
            "release_notes": self.doc_generator._create_release_notes_template,
        }
        
        if template not in template_methods:
            available = ", ".join(template_methods.keys())
            raise ValueError(f"Неизвестный шаблон '{template}'. Доступные: {available}")
        
        metadata, sections = template_methods[template](context)
        
        result_path = self.doc_generator.generate(
            metadata=metadata,
            sections=sections,
            format=doc_format,
            output_path=output_path
        )
        
        print(f"Документ создан: {result_path}")
        return result_path
    
    def index_documents(
        self,
        docs_path: str,
        doc_type: str = "general"
    ) -> int:
        """
        Индексация документов в базу знаний RAG.
        
        Args:
            docs_path: Путь к директории с документами
            doc_type: Тип документов для метаданных
            
        Returns:
            int: Количество проиндексированных документов
        """
        self._lazy_init()
        
        if not self.rag_engine:
            raise RuntimeError("RAG engine недоступен")
        
        docs_path = Path(docs_path)
        
        if not docs_path.exists():
            raise FileNotFoundError(f"Путь не найден: {docs_path}")
        
        # Поддерживаемые форматы
        extensions = ['*.txt', '*.md', '*.rst', '*.json']
        doc_files = []
        
        if docs_path.is_file():
            doc_files = [docs_path]
        else:
            for ext in extensions:
                doc_files.extend(docs_path.rglob(ext))
        
        indexed_count = 0
        
        for doc_file in doc_files:
            print(f"Индексация: {doc_file}")
            
            try:
                content = doc_file.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                content = doc_file.read_text(encoding='latin-1')
            
            document = Document(
                content=content,
                metadata={
                    "source": str(doc_file),
                    "filename": doc_file.name,
                    "doc_type": doc_type
                }
            )
            
            self.rag_engine.add_document(document)
            indexed_count += 1
        
        print(f"Проиндексировано документов: {indexed_count}")
        return indexed_count
    
    def query_knowledge_base(
        self,
        question: str,
        n_results: int = 3
    ) -> Dict[str, Any]:
        """
        Запрос к базе знаний с RAG.
        
        Args:
            question: Вопрос
            n_results: Количество документов контекста
            
        Returns:
            Dict: Ответ с источниками
        """
        self._lazy_init()
        
        if not self.rag_pipeline:
            raise RuntimeError("RAG pipeline недоступен")
        
        print("Поиск в базе знаний...")
        result = self.rag_pipeline.query(
            question=question,
            n_context_docs=n_results
        )
        
        return result


def create_cli_parser() -> argparse.ArgumentParser:
    """Создание парсера CLI аргументов."""
    parser = argparse.ArgumentParser(
        prog="sdlc-automation",
        description="Автоматизация текстовых процессов управления жизненным циклом ПО",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Генерация документации для кода
  python -m src.app.main generate-docs ./src --output docs.docx

  # Анализ требований
  python -m src.app.main analyze-requirements requirements.txt --output analysis.json

  # Создание документа из шаблона
  python -m src.app.main create-doc srs context.json --output srs.docx

  # Генерация тест-кейсов
  python -m src.app.main generate-tests "Авторизация пользователя" --output tests.json

  # Индексация документов для RAG
  python -m src.app.main index-docs ./docs

  # Запрос к базе знаний
  python -m src.app.main query "Как работает авторизация?"

  # Запуск веб-интерфейса
  python -m src.app.main web --port 8080
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Доступные команды")
    
    # Команда: generate-docs
    docs_parser = subparsers.add_parser(
        "generate-docs",
        help="Генерация документации для кода"
    )
    docs_parser.add_argument(
        "code_path",
        help="Путь к файлу или директории с кодом"
    )
    docs_parser.add_argument(
        "--output", "-o",
        required=True,
        help="Путь для сохранения документации"
    )
    docs_parser.add_argument(
        "--type", "-t",
        choices=["technical", "user", "api"],
        default="technical",
        help="Тип документации (по умолчанию: technical)"
    )
    docs_parser.add_argument(
        "--format", "-f",
        choices=["docx", "pdf"],
        default="docx",
        help="Формат вывода (по умолчанию: docx)"
    )
    
    # Команда: analyze-requirements
    req_parser = subparsers.add_parser(
        "analyze-requirements",
        help="Анализ файла с требованиями"
    )
    req_parser.add_argument(
        "requirements_file",
        help="Путь к файлу с требованиями"
    )
    req_parser.add_argument(
        "--output", "-o",
        help="Путь для сохранения результатов анализа (JSON)"
    )
    
    # Команда: generate-tests
    tests_parser = subparsers.add_parser(
        "generate-tests",
        help="Генерация тест-кейсов"
    )
    tests_parser.add_argument(
        "feature",
        help="Описание функциональности для тестирования"
    )
    tests_parser.add_argument(
        "--output", "-o",
        help="Путь для сохранения тест-кейсов (JSON)"
    )
    tests_parser.add_argument(
        "--type", "-t",
        choices=["functional", "integration", "e2e"],
        default="functional",
        help="Тип тестов (по умолчанию: functional)"
    )
    
    # Команда: release-notes
    release_parser = subparsers.add_parser(
        "release-notes",
        help="Генерация release notes"
    )
    release_parser.add_argument(
        "commits_file",
        help="Файл со списком коммитов"
    )
    release_parser.add_argument(
        "--version", "-v",
        required=True,
        help="Номер версии"
    )
    release_parser.add_argument(
        "--output", "-o",
        required=True,
        help="Путь для сохранения"
    )
    release_parser.add_argument(
        "--format", "-f",
        choices=["docx", "pdf", "md"],
        default="docx",
        help="Формат вывода (по умолчанию: docx)"
    )
    
    # Команда: create-doc
    create_parser = subparsers.add_parser(
        "create-doc",
        help="Создание документа из шаблона"
    )
    create_parser.add_argument(
        "template",
        choices=["srs", "test_plan", "technical_doc", "release_notes"],
        help="Имя шаблона"
    )
    create_parser.add_argument(
        "context_file",
        help="JSON файл с данными для заполнения шаблона"
    )
    create_parser.add_argument(
        "--output", "-o",
        required=True,
        help="Путь для сохранения документа"
    )
    create_parser.add_argument(
        "--format", "-f",
        choices=["docx", "pdf"],
        default="docx",
        help="Формат вывода (по умолчанию: docx)"
    )
    
    # Команда: index-docs
    index_parser = subparsers.add_parser(
        "index-docs",
        help="Индексация документов в базу знаний"
    )
    index_parser.add_argument(
        "docs_path",
        help="Путь к директории с документами"
    )
    index_parser.add_argument(
        "--type", "-t",
        default="general",
        help="Тип документов для метаданных"
    )
    
    # Команда: query
    query_parser = subparsers.add_parser(
        "query",
        help="Запрос к базе знаний"
    )
    query_parser.add_argument(
        "question",
        help="Вопрос для поиска"
    )
    query_parser.add_argument(
        "--results", "-n",
        type=int,
        default=3,
        help="Количество документов контекста"
    )
    
    # Команда: web
    web_parser = subparsers.add_parser(
        "web",
        help="Запуск веб-интерфейса"
    )
    web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Хост для запуска (по умолчанию: 127.0.0.1)"
    )
    web_parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="Порт для запуска (по умолчанию: 8080)"
    )
    
    # Общие аргументы
    parser.add_argument(
        "--data-dir",
        default="./data",
        help="Директория для данных приложения"
    )
    parser.add_argument(
        "--verbose", "-V",
        action="store_true",
        help="Подробный вывод"
    )
    
    return parser


def run_web_interface(host: str, port: int, app: SDLCAutomationApp):
    """Запуск веб-интерфейса на Gradio."""
    try:
        import gradio as gr
    except ImportError:
        print("Для веб-интерфейса установите gradio: pip install gradio")
        sys.exit(1)
    
    def generate_docs_ui(code_text: str, doc_type: str) -> str:
        """UI функция для генерации документации."""
        if not code_text.strip():
            return "Введите код для документирования"
        
        app._lazy_init()
        
        if app.llm_service:
            return app.llm_service.generate_documentation(
                code=code_text,
                doc_type=doc_type
            )
        return "LLM сервис недоступен"
    
    def analyze_req_ui(requirements: str) -> str:
        """UI функция для анализа требований."""
        if not requirements.strip():
            return "Введите требования для анализа"
        
        app._lazy_init()
        
        if app.llm_service:
            result = app.llm_service.analyze_requirements(requirements)
            return json.dumps(result, ensure_ascii=False, indent=2)
        return "LLM сер��ис недоступен"
    
    def generate_tests_ui(feature: str, test_type: str) -> str:
        """UI функция для генерации тестов."""
        if not feature.strip():
            return "Введите описание функциональности"
        
        app._lazy_init()
        
        if app.llm_service:
            result = app.llm_service.generate_test_cases(feature, test_type)
            return json.dumps(result, ensure_ascii=False, indent=2)
        return "LLM сервис недоступен"
    
    def query_kb_ui(question: str) -> str:
        """UI функция для запроса к базе знаний."""
        if not question.strip():
            return "Введите вопрос"
        
        try:
            result = app.query_knowledge_base(question)
            return f"**Ответ:**\n\n{result['answer']}\n\n**Источники:** {', '.join(result.get('sources', []))}"
        except Exception as e:
            return f"Ошибка: {e}"
    
    # Создание интерфейса
    with gr.Blocks(title="SDLC Automation Tool") as interface:
        gr.Markdown("# 🛠️ SDLC Automation Tool")
        gr.Markdown("Автоматизация текстовых процессов управления жизненным циклом ПО")
        
        with gr.Tabs():
            # Вкладка: Документация
            with gr.TabItem("📄 Генерация документации"):
                with gr.Row():
                    with gr.Column():
                        code_input = gr.Textbox(
                            label="Исходный код",
                            placeholder="Вставьте код для документирования...",
                            lines=15
                        )
                        doc_type = gr.Dropdown(
                            choices=["technical", "user", "api"],
                            value="technical",
                            label="Тип документации"
                        )
                        gen_btn = gr.Button("Сгенерировать", variant="primary")
                    
                    with gr.Column():
                        doc_output = gr.Textbox(
                            label="Документация",
                            lines=20
                        )
                
                gen_btn.click(
                    generate_docs_ui,
                    inputs=[code_input, doc_type],
                    outputs=doc_output
                )
            
            # Вкладка: Анализ требований
            with gr.TabItem("📋 Анализ требований"):
                with gr.Row():
                    with gr.Column():
                        req_input = gr.Textbox(
                            label="Требования",
                            placeholder="Введите текст требований...",
                            lines=10
                        )
                        analyze_btn = gr.Button("Анализировать", variant="primary")
                    
                    with gr.Column():
                        req_output = gr.Textbox(
                            label="Результат анализа (JSON)",
                            lines=15
                        )
                
                analyze_btn.click(
                    analyze_req_ui,
                    inputs=req_input,
                    outputs=req_output
                )
            
            # Вкладка: Тест-кейсы
            with gr.TabItem("🧪 Генерация тестов"):
                with gr.Row():
                    with gr.Column():
                        feature_input = gr.Textbox(
                            label="Описание функциональности",
                            placeholder="Опишите функцию для тестирования...",
                            lines=5
                        )
                        test_type = gr.Dropdown(
                            choices=["functional", "integration", "e2e"],
                            value="functional",
                            label="Тип тестов"
                        )
                        test_btn = gr.Button("Сгенерировать тесты", variant="primary")
                    
                    with gr.Column():
                        test_output = gr.Textbox(
                            label="Тест-кейсы (JSON)",
                            lines=15
                        )
                
                test_btn.click(
                    generate_tests_ui,
                    inputs=[feature_input, test_type],
                    outputs=test_output
                )
            
            # Вкладка: База знани��
            with gr.TabItem("🔍 База знаний (RAG)"):
                with gr.Row():
                    with gr.Column():
                        question_input = gr.Textbox(
                            label="Вопрос",
                            placeholder="Задайте вопрос по базе знаний...",
                            lines=3
                        )
                        query_btn = gr.Button("Найти ответ", variant="primary")
                    
                    with gr.Column():
                        answer_output = gr.Markdown(label="Ответ")
                
                query_btn.click(
                    query_kb_ui,
                    inputs=question_input,
                    outputs=answer_output
                )
        
        gr.Markdown("---")
        gr.Markdown("*Разработано в рамках ВКР: 'Разработка ПО для автоматизации текстовых процессов управления жизненным циклом ПО'*")
    
    print(f"Запуск веб-интерфейса на http://{host}:{port}")
    interface.launch(server_name=host, server_port=port)


def main():
    """Главная функция CLI."""
    parser = create_cli_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Создание приложения
    app = SDLCAutomationApp(data_dir=args.data_dir)
    
    try:
        if args.command == "generate-docs":
            app.generate_documentation(
                code_path=args.code_path,
                output_path=args.output,
                doc_type=args.type,
                format=args.format
            )
        
        elif args.command == "analyze-requirements":
            result = app.analyze_requirements(
                requirements_file=args.requirements_file,
                output_path=args.output
            )
            if not args.output:
                print(json.dumps(result, ensure_ascii=False, indent=2))
        
        elif args.command == "generate-tests":
            result = app.generate_test_cases(
                feature_description=args.feature,
                output_path=args.output,
                test_type=args.type
            )
            if not args.output:
                print(json.dumps(result, ensure_ascii=False, indent=2))
        
        elif args.command == "release-notes":
            app.generate_release_notes(
                commits_file=args.commits_file,
                version=args.version,
                output_path=args.output,
                format=args.format
            )
        
        elif args.command == "create-doc":
            app.create_document(
                template=args.template,
                context_file=args.context_file,
                output_path=args.output,
                format=args.format
            )
        
        elif args.command == "index-docs":
            app.index_documents(
                docs_path=args.docs_path,
                doc_type=args.type
            )
        
        elif args.command == "query":
            result = app.query_knowledge_base(
                question=args.question,
                n_results=args.results
            )
            print(f"\nОтвет: {result['answer']}")
            if result.get('sources'):
                print(f"\nИсточники: {', '.join(result['sources'])}")
        
        elif args.command == "web":
            run_web_interface(args.host, args.port, app)
    
    except FileNotFoundError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if args.verbose if hasattr(args, 'verbose') else False:
            raise
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()