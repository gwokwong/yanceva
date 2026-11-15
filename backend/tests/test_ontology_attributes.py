import pytest
from pydantic import ValidationError

from app.scenarios import get_scenario
from app.services.graph_store.graphiti_store import (
    build_edge_type_models,
    build_entity_type_models,
)
from app.services.ontology_generator import OntologyGenerator
from app.utils.ontology import (
    MAX_ONTOLOGY_ATTRIBUTES,
    MAX_ONTOLOGY_SOURCE_TARGETS,
    MAX_ONTOLOGY_TYPES,
    normalize_ontology_attribute,
    normalize_ontology_attributes,
)


def test_normalize_string_attribute():
    assert normalize_ontology_attribute("role") == {
        "name": "role",
        "type": "text",
        "description": "role",
    }


def test_preserve_valid_dictionary_attribute():
    original = {"name": "role", "type": "text", "description": "Public role"}
    assert normalize_ontology_attribute(original) == original
    assert normalize_ontology_attribute(original) is not original


def test_reject_unusable_attribute_shapes():
    for value in (None, 7, [], {}, {"name": None}, {"name": ""}, "   "):
        assert normalize_ontology_attribute(value) is None


def test_attribute_list_is_non_empty_and_capped():
    assert normalize_ontology_attributes(None) == [{
        "name": "details",
        "type": "text",
        "description": "Additional details about this ontology type.",
    }]

    attributes = [None] + [f"field_{index}" for index in range(12)]
    normalized = normalize_ontology_attributes(attributes)

    assert len(normalized) == MAX_ONTOLOGY_ATTRIBUTES
    assert [attribute["name"] for attribute in normalized] == [
        f"field_{index}" for index in range(MAX_ONTOLOGY_ATTRIBUTES)
    ]


def test_generator_normalizes_entity_and_edge_attributes():
    result = OntologyGenerator(llm_client=object())._validate_and_process({
        "entity_types": [{"name": "speaker", "attributes": ["role", None]}],
        "edge_types": [{"name": "quotes", "attributes": ["source_url", {}]}],
    })

    assert result["entity_types"][0]["attributes"] == [{
        "name": "role",
        "type": "text",
        "description": "role",
    }]
    assert result["edge_types"][0]["attributes"] == [{
        "name": "source_url",
        "type": "text",
        "description": "source_url",
    }]


def test_generator_adds_a_property_to_empty_custom_types():
    result = OntologyGenerator(llm_client=object())._validate_and_process({
        "entity_types": [{"name": "speaker", "attributes": []}],
        "edge_types": [{"name": "quotes", "attributes": []}],
    })

    assert result["entity_types"][0]["attributes"][0]["name"] == "details"
    assert result["edge_types"][0]["attributes"][0]["name"] == "details"


# ============== Graphiti 自定义类型模型构建 ==============

def test_build_entity_type_models_creates_pydantic_models_with_safe_names():
    ontology = {
        "entity_types": [
            {
                "name": "Speaker",
                "description": "A speaking entity",
                "attributes": ["role", "graph_id"],
            },
        ],
        "edge_types": [],
    }

    models = build_entity_type_models(ontology)

    assert set(models) == {"Speaker"}
    speaker = models["Speaker"]
    assert set(speaker.__annotations__) == {"role", "entity_graph_id"}

    instance = speaker(role="host", entity_graph_id="g-1")
    assert instance.role == "host"
    assert instance.entity_graph_id == "g-1"

    with pytest.raises(ValidationError):
        speaker(role=123, entity_graph_id=None)  # 非 str 属性应被拒绝


def test_build_entity_type_models_caps_at_max_types():
    ontology = {
        "entity_types": [
            {"name": f"Type{index}", "attributes": []}
            for index in range(MAX_ONTOLOGY_TYPES + 5)
        ],
        "edge_types": [],
    }

    models = build_entity_type_models(ontology)
    assert len(models) == MAX_ONTOLOGY_TYPES


def test_build_edge_type_models_uses_pascal_case_class_names():
    ontology = {
        "entity_types": [],
        "edge_types": [
            {"name": "WORKS_FOR", "description": "employment", "attributes": []},
        ],
    }

    models = build_edge_type_models(ontology)
    assert set(models) == {"WORKS_FOR"}
    assert models["WORKS_FOR"].__name__ == "WorksFor"


def test_builder_set_ontology_delegates_to_store():
    """GraphBuilderService.set_ontology 只做委托，本体在摄取时转换为模型。"""

    class FakeStore:
        def __init__(self):
            self.calls = []

        def set_ontology(self, graph_id, ontology):
            self.calls.append((graph_id, ontology))

    from app.services.graph_builder import GraphBuilderService

    builder = object.__new__(GraphBuilderService)
    builder.store = FakeStore()

    ontology = {"entity_types": [{"name": "Speaker", "attributes": ["role", None]}]}
    builder.set_ontology("graph-id", ontology)

    assert builder.store.calls == [("graph-id", ontology)]


def test_scenarios_provide_distinct_ontology_prompts():
    opinion = get_scenario("public_opinion")
    ecommerce = get_scenario("ecommerce")

    assert opinion.ontology_system_prompt != ecommerce.ontology_system_prompt
    assert "社交媒体舆论模拟" in opinion.ontology_system_prompt
    assert "电商新品上市预演" in ecommerce.ontology_system_prompt
    # 电商场景的知识节点不生成 Agent
    assert "product" in ecommerce.knowledge_node_types
    assert not opinion.is_knowledge_node("Product")
    assert ecommerce.is_knowledge_node("Product")
    assert ecommerce.is_agent_entity("Consumer")
    assert not ecommerce.is_agent_entity("Product")
