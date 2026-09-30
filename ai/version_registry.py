"""
ai/version_registry.py - Centralized Minecraft Version Registry and Context

Provides structured models and registry for managing Minecraft Java Edition versions,
capabilities, data pack formats, and directory layout conventions.

This architecture centralizes version-specific metadata to prevent scattered version
conditionals across the codebase.
"""

from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class VersionMetadata(BaseModel):
    """
    Declarative capabilities and configuration for a specific Minecraft Java Edition version.
    """
    model_config = ConfigDict(extra="allow", frozen=True)

    version_id: str = Field(..., description="Minecraft Java Edition version string (e.g. '1.21.11')")
    pack_format: int = Field(..., description="Major data pack format integer for pack.mcmeta (e.g. 94)")
    min_format: Optional[List[int]] = Field(
        default=None,
        description="Minimum supported data pack format [major, minor] if format ranges are supported"
    )
    max_format: Optional[List[int]] = Field(
        default=None,
        description="Maximum supported data pack format [major, minor] if format ranges are supported"
    )
    supports_format_range: bool = Field(
        default=True,
        description="Whether pack.mcmeta supports min_format / max_format arrays (introduced in 1.20.2+)"
    )
    directory_layout: str = Field(
        default="singular",
        description="Data pack directory naming convention: 'singular' (1.21+) or 'plural' (1.20.4-)"
    )
    attribute_format: str = Field(
        default="namespaced",
        description="Attribute identifier style: 'namespaced' (1.21+) or 'legacy' (1.20-)"
    )
    modifier_id_format: str = Field(
        default="string",
        description="Attribute modifier ID format: 'string' (namespaced string in 1.21+) or 'uuid' (1.20-)"
    )
    recipe_result_format: str = Field(
        default="id_count",
        description="Recipe result item specification format: 'id_count' (1.21+) or 'item_count' (1.20.4-)"
    )
    server_jar_path: Optional[Path] = Field(
        default=None,
        description="Resolved path to local Minecraft server JAR if available"
    )
    data_pack_version: Optional[str] = Field(
        default=None,
        description="Semantic data pack version string (e.g. '94.1')"
    )
    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of this version"
    )


class VersionRegistry:
    """
    Central registry of supported Minecraft versions and their capabilities.
    """

    def __init__(self):
        self._versions: Dict[str, VersionMetadata] = {}
        self._default_version_id: str = "1.21.11"
        self._init_defaults()

    def _init_defaults(self) -> None:
        """
        Registers officially supported baseline versions.
        For Step 23 (State A), Minecraft Java 1.21.11 is the only officially supported version.
        """
        repo_root = Path(__file__).resolve().parent.parent
        server_jar = repo_root / "versions" / "1.21.11" / "server-1.21.11.jar"
        if not server_jar.exists():
            fallback_jar = repo_root / "source" / "1.21.11" / "server.jar"
            if fallback_jar.exists():
                server_jar = fallback_jar

        self.register(
            VersionMetadata(
                version_id="1.21.11",
                pack_format=94,
                min_format=[94, 0],
                max_format=[94, 1],
                supports_format_range=True,
                directory_layout="singular",
                attribute_format="namespaced",
                modifier_id_format="string",
                recipe_result_format="id_count",
                data_pack_version="94.1",
                server_jar_path=server_jar if server_jar.exists() else None,
                description="Minecraft Java Edition 1.21.11 (Data Pack 94.1)"
            )
        )

    def register(self, metadata: VersionMetadata) -> None:
        """
        Registers a version's metadata deterministically.
        """
        self._versions[metadata.version_id] = metadata

    def get(self, version_id: str) -> VersionMetadata:
        """
        Retrieves metadata for the specified version.
        Raises ValueError if the version is unknown or unsupported.
        """
        v_clean = str(version_id).strip()
        if v_clean not in self._versions:
            supported = ", ".join(self.get_supported_versions())
            raise ValueError(
                f"Unsupported Minecraft version '{v_clean}'. "
                f"Officially supported version(s): {supported}"
            )
        return self._versions[v_clean]

    def get_default(self) -> VersionMetadata:
        """
        Returns metadata for the default Minecraft version (1.21.11).
        """
        return self._versions[self._default_version_id]

    def get_supported_versions(self) -> List[str]:
        """
        Returns a sorted list of registered, officially supported version IDs.
        """
        return sorted(list(self._versions.keys()))

    def is_supported(self, version_id: Optional[str]) -> bool:
        """
        Checks whether the specified version is officially registered and supported.
        """
        if not version_id:
            return False
        return str(version_id).strip() in self._versions

    def set_default(self, version_id: str) -> None:
        """
        Sets the default version ID if registered.
        """
        if not self.is_supported(version_id):
            raise ValueError(f"Cannot set default to unregistered version '{version_id}'.")
        self._default_version_id = str(version_id).strip()


class VersionContext(BaseModel):
    """
    Resolved execution context representing a target Minecraft version for components.
    Eliminates manual version string parsing and provides typed access to version capabilities.
    """
    model_config = ConfigDict(extra="allow", frozen=True)

    metadata: VersionMetadata = Field(..., description="Target version capabilities metadata")

    @property
    def version_id(self) -> str:
        return self.metadata.version_id

    @property
    def pack_format(self) -> int:
        return self.metadata.pack_format

    @property
    def min_format(self) -> Optional[List[int]]:
        return self.metadata.min_format

    @property
    def max_format(self) -> Optional[List[int]]:
        return self.metadata.max_format

    @property
    def supports_format_range(self) -> bool:
        return self.metadata.supports_format_range

    @property
    def directory_layout(self) -> str:
        return self.metadata.directory_layout

    @property
    def attribute_format(self) -> str:
        return self.metadata.attribute_format

    @property
    def modifier_id_format(self) -> str:
        return self.metadata.modifier_id_format

    @property
    def recipe_result_format(self) -> str:
        return self.metadata.recipe_result_format

    @property
    def server_jar_path(self) -> Optional[Path]:
        return self.metadata.server_jar_path

    @property
    def data_pack_version(self) -> Optional[str]:
        return self.metadata.data_pack_version

    @classmethod
    def from_version(
        cls,
        version: Optional[str] = None,
        registry: Optional[VersionRegistry] = None
    ) -> "VersionContext":
        """
        Factory method to resolve a VersionContext from a version string.
        If version is None, resolves to the default registered version.
        Raises ValueError if version is unsupported.
        """
        active_registry = registry or get_version_registry()
        if version is None or str(version).strip() == "":
            meta = active_registry.get_default()
        else:
            meta = active_registry.get(str(version).strip())
        return cls(metadata=meta)


# Global singleton instance
_GLOBAL_VERSION_REGISTRY: Optional[VersionRegistry] = None


def get_version_registry() -> VersionRegistry:
    """
    Retrieves the global VersionRegistry singleton.
    """
    global _GLOBAL_VERSION_REGISTRY
    if _GLOBAL_VERSION_REGISTRY is None:
        _GLOBAL_VERSION_REGISTRY = VersionRegistry()
    return _GLOBAL_VERSION_REGISTRY


def get_default_version() -> str:
    """
    Convenience function returning the default version ID string ('1.21.11').
    """
    return get_version_registry().get_default().version_id
