from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="allow")

    level: str = Field(..., description="'error' or 'warning'")
    code: str = Field(..., description="Machine-readable issue code")
    message: str = Field(..., description="Human-readable description of the issue")
    file: Optional[str] = Field(default=None, description="Relative path of the offending file")


class ValidationCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Descriptive name of the validation check")
    passed: bool = Field(..., description="Whether the check succeeded")
    message: Optional[str] = Field(default=None, description="Additional context or outcome details")
    file: Optional[str] = Field(default=None, description="Relevant file checked")


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'valid' or 'invalid'")
    target_path: str = Field(..., description="Path to the validated datapack directory or ZIP")
    is_zip: bool = Field(default=False, description="True if target was a ZIP archive")
    errors: List[ValidationIssue] = Field(default_factory=list, description="Validation errors preventing use")
    warnings: List[ValidationIssue] = Field(default_factory=list, description="Non-fatal warnings or advisories")
    checks: List[ValidationCheck] = Field(default_factory=list, description="All executed validation checks")

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and self.status == "valid"

    def summary(self) -> str:
        res = [
            f"Validation Result: {self.status.upper()}",
            f"Target: {self.target_path} ({'ZIP' if self.is_zip else 'Directory'})",
            f"Checks: {len(self.checks)} executed, {sum(1 for c in self.checks if c.passed)} passed, {sum(1 for c in self.checks if not c.passed)} failed",
            f"Errors: {len(self.errors)}",
            f"Warnings: {len(self.warnings)}"
        ]
        if self.errors:
            res.append("\nErrors:")
            for err in self.errors:
                loc = f" in {err.file}" if err.file else ""
                res.append(f"  - [{err.code}]{loc}: {err.message}")
        if self.warnings:
            res.append("\nWarnings:")
            for warn in self.warnings:
                loc = f" in {warn.file}" if warn.file else ""
                res.append(f"  - [{warn.code}]{loc}: {warn.message}")
        return "\n".join(res)
