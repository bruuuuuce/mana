"""Static, framework-owned adapter selection. Never import target-project code."""

from .java_spring import JavaSpringAdapter

ADAPTERS = (JavaSpringAdapter(),)
