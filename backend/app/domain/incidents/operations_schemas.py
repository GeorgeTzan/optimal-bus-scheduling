from typing import Annotated,Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,StringConstraints,model_validator
Text=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=2000)]
Identity=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=100)]

class Mutation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=0,strict=True)
    request_id:UUID

class ReportRequest(Mutation):
    publication_id:Identity
    trip_id:Identity
    kind:Literal['delay','breakdown','note','departure','completion']
    description:Text
    delay_minutes:int|None=Field(default=None,ge=0,le=1440,strict=True)

    @model_validator(mode='after')
    def applicable_minutes(self):
        if (self.kind=='delay') != (self.delay_minutes is not None):
            raise ValueError('Enter delay minutes only for a delay report.')
        return self

class ResolutionRequest(Mutation):
    note:Text
