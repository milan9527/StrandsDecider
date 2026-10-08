from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoulQuestion(StrictModel):
    type: Literal["noul"]
    instructions: Text
    criteria: dict[Literal["true", "false"], Text] | None = None


class ChoiceQuestion(StrictModel):
    type: Literal["choice"]
    instructions: Text
    criteria: dict[Label, Text | None] = Field(min_length=2, max_length=12)


class ScoreQuestion(StrictModel):
    type: Literal["score"]
    instructions: Text
    criteria: list[Text] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def unique_levels(self):
        if len(set(self.criteria)) != len(self.criteria):
            raise ValueError("评分等级不能重复")
        return self


Question = Annotated[NoulQuestion | ChoiceQuestion | ScoreQuestion, Field(discriminator="type")]


class DecisionRequest(StrictModel):
    mode: Literal["example", "live"] = "example"
    measure_decisions: bool = False
    example_id: str | None = None
    state: str = Field(max_length=12000)
    questions: dict[Label, Question] = Field(min_length=1, max_length=8)

    def wire_payload(self) -> dict:
        return {
            "state": self.state,
            "questions": {
                key: value.model_dump(exclude_none=True) for key, value in self.questions.items()
            },
        }


class GuardRequest(StrictModel):
    mode: Literal["example", "live"] = "example"
    measure_decisions: bool = False
    message: Text
    location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    threshold: float = Field(default=0.45, ge=0.05, le=0.95, allow_inf_nan=False)
