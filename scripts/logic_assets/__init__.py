"""One-source TripLens logic diagram assets."""
from .model import validate_model
from .drawio import build_document, create_index
from .drawing_master import create_drawing_master


def make_repository(tags, rules, census, *, layout_xml=None):
    model=validate_model(tags,rules,census)
    xml=build_document(model,layout_xml)
    index=create_index(model,xml)
    drawing_master=create_drawing_master(
        xml,
        canonical_tags={tag: row['canonical_tag'] for tag,row in model['tags'].items() if row.get('canonical_tag')},
        file_path='logic_diagrams/TripLens_Logic_Master_Current_V8.drawio',
        aliases=[
            'generated/logic/TripLens_Logic_Master_Current_V8.drawio',
            'apps/web/public/logic-assets/TripLens_Logic_Master_Current_V8.drawio',
        ],
    )
    from .build import derive_views
    return {'xml':xml,'index':index,'drawing_master':drawing_master,
            'model':model,'derived':derive_views(model,index)}


def publish_repository(repository, target):
    from .build import publish_repository as publish
    return publish(repository,target)
