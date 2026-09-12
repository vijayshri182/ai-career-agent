"""Deterministic skill vocabulary, extraction, and semantic matching.

The skill vocabulary and synonym map make extraction fully reproducible. The
semantic matcher is a pluggable protocol: the default is a deterministic
synonym resolver drawn from ``RELATED``. A vector/embeddings-based matcher MAY
be supplied later, but it can only *add* related-skill credit inside the same
explainable framework — it never overrides rules or reads instructions from
untrusted job text.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

# Canonical skill key -> human label. Keys are extracted from job text; labels
# are what the candidate is credited for.
SKILLS: dict[str, str] = {
    # Programming languages
    "python": "Python",
    "java": "Java",
    "golang": "Go (Golang)",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "cpp": "C++",
    "csharp": "C#",
    "scala": "Scala",
    "kotlin": "Kotlin",
    "rust": "Rust",
    "sql": "SQL",
    "shell": "Shell / Bash scripting",
    "bash": "Bash scripting",
    # Frameworks & libraries
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "spring": "Spring",
    "springboot": "Spring Boot",
    "react": "React",
    "reactjs": "React",
    "nextjs": "Next.js",
    "nodejs": "Node.js",
    "angular": "Angular",
    "vuejs": "Vue.js",
    "kafka_consumer": "Kafka consumers/producers",
    "gprc": "gRPC",
    "grpc": "gRPC",
    "celery": "Celery",
    # Cloud & DevOps
    "aws": "AWS",
    "azure": "Microsoft Azure",
    "gcp": "Google Cloud Platform",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "jenkins": "Jenkins",
    "github_actions": "GitHub Actions",
    "gitlab_ci": "GitLab CI",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "opentelemetry": "OpenTelemetry",
    "datadog": "Datadog",
    "elasticsearch": "Elasticsearch",
    "logstash": "Logstash",
    "devsecops": "DevSecOps",
    "ci_cd": "CI/CD pipelines",
    "infrastructure_as_code": "Infrastructure as Code",
    "linux": "Linux",
    # Databases & storage
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "redis": "Redis",
    "mongodb": "MongoDB",
    "cassandra": "Cassandra",
    "dynamodb": "DynamoDB",
    "oracle_db": "Oracle Database",
    "sqlite": "SQLite",
    "bigquery": "BigQuery",
    "s3": "S3 / object storage",
    # Messaging & streaming
    "kafka": "Apache Kafka",
    "rabbitmq": "RabbitMQ",
    "pulsar": "Apache Pulsar",
    "mqtt": "MQTT",
    "amqp": "AMQP",
    # Architecture & engineering practices
    "microservices": "Microservices",
    "distributed_systems": "Distributed systems",
    "event_driven": "Event-driven architecture",
    "rest": "REST APIs",
    "domain_driven_design": "Domain-Driven Design (DDD)",
    "cqrs": "CQRS",
    "api_gateway": "API gateway",
    "message_queues": "Message queues",
    "system_design": "System design",
    "high_availability": "High availability",
    "resilience": "Resilience engineering",
    "load_balancing": "Load balancing",
    "service_mesh": "Service mesh",
    "istio": "Istio",
    "blue_green": "Blue-green deployment",
    "canary": "Canary deployment",
    "circuit_breaker": "Circuit breaker patterns",
    "saga": "Saga / distributed transactions",
    "outbox": "Transactional outbox",
    "monitoring": "Monitoring & observability",
    "observability": "Observability",
    # Telecom
    "5g": "5G",
    "4g": "4G/LTE",
    "lte": "LTE",
    "gsm": "GSM",
    "volte": "VoLTE",
    "voip": "VoIP",
    "sip": "SIP",
    "ims": "IMS",
    "ran": "RAN (Radio Access Network)",
    "core_network": "Core Network",
    "gprs": "GPRS",
    "nrf": "5G/NR",
    "telecom": "Telecom",
    "ocs": "Online Charging System (OCS)",
    "charging": "Charging systems",
    "rating": "Rating & charging",
    "policy_control": "Policy control (PCRF/PCEF)",
    "pcrf": "PCRF",
    # OSS/BSS
    "oss": "OSS (Operations Support Systems)",
    "bss": "BSS (Business Support Systems)",
    "billing": "Billing systems",
    "provisioning": "Service provisioning",
    "activation": "Service activation",
    "crm": "CRM",
    "order_management": "Order management",
    "product_catalog": "Product catalog",
    "inventory": "Service inventory",
    "service_assurance": "Service assurance",
    "nms": "Network Management System (NMS)",
    "revenue_assurance": "Revenue assurance",
    "mediation": "Mediation systems",
    "convergent_billing": "Convergent billing",
    "subscription_management": "Subscription management",
    "metering": "Metering / usage rating",
    # AI / GenAI
    "ai": "Artificial Intelligence (AI)",
    "ml": "Machine Learning (ML)",
    "machine_learning": "Machine Learning",
    "deep_learning": "Deep learning",
    "llm": "Large Language Models (LLMs)",
    "nlp": "Natural Language Processing (NLP)",
    "vector_db": "Vector databases",
    "embeddings": "Embeddings",
    "rag": "Retrieval-Augmented Generation (RAG)",
    "fine_tuning": "Model fine-tuning",
    "prompt_engineering": "Prompt engineering",
    "langchain": "LangChain",
    "genai": "Generative AI",
    "computer_vision": "Computer vision",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    # Management & leadership
    "people_management": "People management",
    "team_leadership": "Team leadership",
    "mentoring": "Mentoring",
    "stakeholder_management": "Stakeholder management",
    "budgeting": "Budgeting",
    "agile": "Agile",
    "scrum": "Scrum",
    "kanban": "Kanban",
    "roadmap": "Product/tech roadmap",
    "hiring": "Hiring",
    "vendor_negotiation": "Vendor negotiation",
    "architectural_leadership": "Architectural leadership",
    # Security
    "oauth2": "OAuth 2.0",
    "oidc": "OpenID Connect (OIDC)",
    "jwt": "JWT",
    "sso": "Single Sign-On (SSO)",
    "tls": "TLS",
    "encryption": "Encryption",
    "zero_trust": "Zero trust",
    "gdpr": "GDPR",
    "soc2": "SOC 2",
    "pen_testing": "Penetration testing",
    "secret_management": "Secret management",
    # Tools & miscellaneous
    "excel": "Excel",
    "powerpoint": "PowerPoint",
    "jira": "Jira",
    "confluence": "Confluence",
    "kubernetes_helm": "Helm",
    "git": "Git",
    "rest_api_design": "REST API design",
    "testing": "Automated testing",
    "pytest": "pytest",
    "unit_testing": "Unit testing",
    "tdd": "Test-Driven Development (TDD)",
}

# Alias -> canonical key. Applied during normalization so near-synonyms collapse.
SYNONYMS: dict[str, str] = {
    "golang": "golang",
    "go (golang)": "golang",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "aws": "aws",
    "amazon web services": "aws",
    "azure": "azure",
    "microsoft azure": "azure",
    "gcp": "gcp",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "postgres": "postgres",
    "postgresql": "postgres",
    "js": "javascript",
    "node": "nodejs",
    "node.js": "nodejs",
    "react": "react",
    "react.js": "react",
    "reactjs": "react",
    "next": "nextjs",
    "next.js": "nextjs",
    "typescript": "typescript",
    "ts": "typescript",
    "machine learning": "machine_learning",
    "ml": "machine_learning",
    "artificial intelligence": "ai",
    "ai/ml": "ai",
    "genai": "genai",
    "generative ai": "genai",
    "llms": "llm",
    "llm": "llm",
    "large language model": "llm",
    "large language models": "llm",
    "retrieval augmented generation": "rag",
    "vector database": "vector_db",
    "vector databases": "vector_db",
    "micro services": "microservices",
    "microservice": "microservices",
    "micro-services": "microservices",
    "distributed systems": "distributed_systems",
    "distributed system": "distributed_systems",
    "event-driven": "event_driven",
    "event driven": "event_driven",
    "ddd": "domain_driven_design",
    "domain driven design": "domain_driven_design",
    "rest api": "rest",
    "rest apis": "rest",
    "api gateway": "api_gateway",
    "c++": "cpp",
    "c#": "csharp",
    "linux": "linux",
    "shell": "shell",
    "bash": "bash",
    "ci cd": "ci_cd",
    "ci/cd": "ci_cd",
    "cicd": "ci_cd",
    "terraform": "terraform",
    "docker": "docker",
    "open telemetry": "opentelemetry",
    "prometheus": "prometheus",
    "grafana": "grafana",
    "5g core": "core_network",
    "5g": "5g",
    "lte": "lte",
    "4g": "lte",
    "oss": "oss",
    "bss": "bss",
    "business support system": "bss",
    "operations support system": "oss",
    "telecom": "telecom",
    "telecommunications": "telecom",
    "telco": "telecom",
    "billing": "billing",
    "rating": "rating",
    "charging": "charging",
    "revenue assurance": "revenue_assurance",
    "provisioning": "provisioning",
    "people management": "people_management",
    "leadership": "team_leadership",
    "leading a team": "team_leadership",
    "mentor": "mentoring",
    "mentoring": "mentoring",
    "oauth": "oauth2",
    "openid connect": "oidc",
    "jwt": "jwt",
    "json web token": "jwt",
    "ssl": "tls",
    "single sign on": "sso",
    "agile": "agile",
    "scrum": "scrum",
    "observability": "observability",
    "monitoring": "monitoring",
}

# Deterministic related-skill map: canonical key -> list of related canonical
# keys (used for transferable-skill credit and never for hard requirements).
RELATED: dict[str, list[str]] = {
    "golang": ["python", "java"],
    "java": ["golang", "kotlin", "python"],
    "python": ["golang", "java", "machine_learning"],
    "typescript": ["javascript", "react"],
    "javascript": ["typescript", "react"],
    "kubernetes": ["docker", "terraform", "aws"],
    "terraform": ["kubernetes", "aws", "azure"],
    "docker": ["kubernetes"],
    "aws": ["azure", "gcp", "terraform", "kubernetes"],
    "azure": ["aws", "gcp"],
    "gcp": ["aws", "azure"],
    "kafka": ["message_queues", "rabbitmq", "pulsar"],
    "rabbitmq": ["message_queues", "kafka"],
    "microservices": ["distributed_systems", "event_driven", "rest"],
    "distributed_systems": ["microservices", "message_queues"],
    "event_driven": ["kafka", "message_queues"],
    "rest": ["microservices", "api_gateway"],
    "fastapi": ["python", "flask", "django"],
    "django": ["python", "flask", "fastapi"],
    "flask": ["python", "fastapi"],
    "react": ["javascript", "typescript"],
    "nodejs": ["javascript", "typescript"],
    "postgres": ["mysql", "sql", "redis"],
    "mysql": ["postgres", "sql"],
    "redis": ["postgres", "message_queues"],
    "mongodb": ["postgres", "cassandra"],
    "machine_learning": ["ai", "deep_learning", "python"],
    "deep_learning": ["machine_learning", "pytorch", "tensorflow"],
    "llm": ["genai", "rag", "nlp", "machine_learning"],
    "nlp": ["llm", "machine_learning"],
    "rag": ["llm", "vector_db", "embeddings"],
    "embeddings": ["vector_db", "rag"],
    "vector_db": ["embeddings", "rag"],
    "genai": ["llm", "rag", "prompt_engineering"],
    "billing": ["bss", "rating", "charging", "convergent_billing"],
    "rating": ["charging", "billing", "metering"],
    "charging": ["rating", "billing", "ocs"],
    "ocs": ["charging", "bss"],
    "oss": ["bss", "service_assurance", "nms", "inventory"],
    "bss": ["oss", "billing", "order_management", "crm"],
    "service_assurance": ["oss", "nms", "monitoring"],
    "nms": ["oss", "service_assurance"],
    "provisioning": ["activation", "order_management"],
    "activation": ["provisioning"],
    "revenue_assurance": ["billing", "rating", "mediation"],
    "mediation": ["billing", "revenue_assurance"],
    "crm": ["bss", "order_management"],
    "order_management": ["crm", "bss"],
    "core_network": ["5g", "lte", "ims", "telecom"],
    "5g": ["core_network", "lte", "ran", "telecom"],
    "lte": ["5g", "ran", "volte"],
    "ims": ["sip", "volte", "core_network"],
    "sip": ["voip", "ims"],
    "volte": ["ims", "lte"],
    "telecom": ["5g", "lte", "oss", "bss", "core_network"],
    "team_leadership": ["people_management", "mentoring", "stakeholder_management"],
    "people_management": ["team_leadership", "hiring"],
    "mentoring": ["team_leadership"],
    "stakeholder_management": ["team_leadership", "vendor_negotiation"],
    "agile": ["scrum", "kanban"],
    "scrum": ["agile", "kanban"],
    "prompt_engineering": ["llm", "genai"],
    "langchain": ["python", "llm"],
    "pytorch": ["tensorflow", "machine_learning", "python"],
    "tensorflow": ["pytorch", "machine_learning"],
    "monitoring": ["observability", "prometheus", "grafana"],
    "observability": ["monitoring", "opentelemetry"],
    "opentelemetry": ["observability"],
    "jwt": ["oauth2", "oidc", "sso"],
    "oauth2": ["oidc", "jwt", "sso"],
    "oidc": ["oauth2", "jwt", "sso"],
    "sso": ["oauth2", "oidc", "jwt"],
}


def canonical_skill(name: str) -> str | None:
    """Normalize a raw skill name to its canonical key (or ``None``)."""
    normalized = _normalize_term(name)
    if not normalized:
        return None
    return SYNONYMS.get(normalized) or (normalized if normalized in SKILLS else None)


def _normalize_term(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9+#]", " ", text)
    return " ".join(text.split())


class SemanticSkillMatcher(ABC):
    """Optional semantic-skill augmentation. Default resolves deterministic aliases.

    A vector-based implementation may be substituted later; it may only broaden
    *related* skill credit and is forbidden from weakening hard requirements.
    """

    @abstractmethod
    def related_skills(self, skill: str, *, limit: int = 4) -> list[str]:
        """Return canonical skill keys related to ``skill`` (may be empty)."""


class SynonymSkillMatcher(SemanticSkillMatcher):
    def related_skills(self, skill: str, *, limit: int = 4) -> list[str]:
        canonical = canonical_skill(skill)
        if canonical is None:
            return []
        return [item for item in RELATED.get(canonical, []) if item != canonical][:limit]


class NoopSkillMatcher(SemanticSkillMatcher):
    def related_skills(self, skill: str, *, limit: int = 4) -> list[str]:
        return []


# Text patterns (as they appear in job postings) -> canonical skill key.
EXTRACTION_PATTERNS: dict[str, str] = {
    "c++": "cpp",
    "c#": "csharp",
    "k8s": "kubernetes",
    "go (golang)": "golang",
    "golang": "golang",
    "node.js": "nodejs",
    "react.js": "react",
    "next.js": "nextjs",
    "ci/cd": "ci_cd",
    "amazon web services": "aws",
    "google cloud platform": "gcp",
    "microsoft azure": "azure",
    "rest api": "rest",
    "api gateway": "api_gateway",
    "machine learning": "machine_learning",
    "artificial intelligence": "ai",
    "generative ai": "genai",
    "retrieval augmented generation": "rag",
    "large language models": "llm",
    "large language model": "llm",
    "domain driven design": "domain_driven_design",
    "distributed systems": "distributed_systems",
    "event driven": "event_driven",
    "people management": "people_management",
    "team leadership": "team_leadership",
    "5g": "5g",
    "4g/lte": "lte",
    "wireless": "telecom",
}


class SkillExtractor:
    """Deterministic keyword extraction of the known skill vocabulary."""

    def __init__(self) -> None:
        pattern_keys: dict[str, str] = dict(EXTRACTION_PATTERNS)
        for key in SKILLS:
            pattern_keys.setdefault(key.replace("_", " "), key)
        self._patterns: list[tuple[str, re.Pattern[str]]] = [
            (key, re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE))
            for phrase, key in pattern_keys.items()
        ]

    def extract(self, text: str | None) -> set[str]:
        """Return canonical skill keys present in ``text``."""
        if not text:
            return set()
        lowered = text.lower()
        found: set[str] = set()
        for key, pattern in self._patterns:
            if pattern.search(lowered):
                found.add(key)
        return found
