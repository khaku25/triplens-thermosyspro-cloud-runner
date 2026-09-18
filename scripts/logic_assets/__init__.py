"""One-source TripLens logic diagram assets."""
from .model import validate_model
from .drawio import build_document, create_index


def make_repository(tags, rules, census, *, layout_xml=None):
    model=validate_model(tags,rules,census)
    xml=build_document(model,layout_xml)
    index=create_index(model,xml)
    from .build import derive_views
    return {'xml':xml,'index':index,'model':model,'derived':derive_views(model,index)}


def publish_repository(repository, target):
    from .build import publish_repository as publish
    return publish(repository,target)
