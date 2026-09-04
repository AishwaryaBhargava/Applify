"""Shared Azure OpenAI client.

Azure AI Foundry speaks the OpenAI API, so the ``openai`` SDK's AzureOpenAI
class is the client. One instance is shared by the analysis and output services.
"""

from functools import lru_cache

from openai import AzureOpenAI

from app.core.config import settings


@lru_cache
def get_azure_client() -> AzureOpenAI:
    """Return the process-wide AzureOpenAI client.

    Built lazily so importing this module never requires Azure credentials.
    """
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


def get_deployment_name() -> str:
    """Return the GPT-4o deployment name to pass as the ``model`` argument."""
    return settings.azure_gpt4o_deployment
