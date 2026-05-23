from enum import Enum

class Runtime(Enum):
    PYTHON = "python"
    NODEJS = "nodejs"

class Framework(Enum):
    FASTAPI = "fastapi"
    FLASK = "flask"
    DJANGO = "django"
    EXPRESS = "express"
    NEXTJS = "nextjs"
    REACT = "react"

class ServiceType(Enum):
    BACKEND_API     = "backend_api"
    FRONTEND_SSR    = "frontend_ssr"
    FRONTEND_STATIC = "frontend_static"

class DeployMode(Enum):
    FREE = "free"
    PROD = "prod"

