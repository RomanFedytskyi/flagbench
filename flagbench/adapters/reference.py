"""
Reference adapter — wraps ReferenceResolver.
This is the baseline; it scores accuracy=1.0 by definition.
"""
from flagbench.resolver import ReferenceResolver
from flagbench.schema import ResolutionInput, ResolutionOutput

_resolver = ReferenceResolver()


def resolve(inp: ResolutionInput) -> ResolutionOutput:
    return _resolver.resolve(inp)
