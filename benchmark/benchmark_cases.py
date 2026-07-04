from image_pipeline_common.models import PipelineStep


BENCHMARK_CASES: dict[str, list[PipelineStep]] = {
    "light_grayscale": [
        PipelineStep(operation="grayscale", parameters={}),
    ],
    "light_thumbnail": [
        PipelineStep(
            operation="thumbnail",
            parameters={"width": 600, "height": 600},
        ),
    ],
    "light_rotate": [
        PipelineStep(
            operation="rotate",
            parameters={"angle": 90},
        ),
    ],
    "medium_blur": [
        PipelineStep(
            operation="blur",
            parameters={"radius": 5},
        ),
    ],
    "medium_sharpen": [
        PipelineStep(
            operation="sharpen",
            parameters={"factor": 2.0},
        ),
    ],
    "medium_contrast": [
        PipelineStep(
            operation="contrast",
            parameters={"factor": 2.0},
        ),
    ],
    "medium_edge_detect": [
        PipelineStep(operation="edge_detect", parameters={}),
    ],
    "medium_emboss": [
        PipelineStep(operation="emboss", parameters={}),
    ],
    "region_blur": [
        PipelineStep(
            operation="blur",
            parameters={
                "radius": 8,
                "region": {
                    "x": 100,
                    "y": 100,
                    "width": 400,
                    "height": 300,
                },
            },
        ),
    ],
    "heavy_blur_repeat": [
        PipelineStep(
            operation="blur",
            parameters={"radius": 8, "repeat": 10},
        ),
    ],
    "heavy_mixed_pipeline": [
        PipelineStep(
            operation="thumbnail",
            parameters={"width": 1200, "height": 1200},
        ),
        PipelineStep(
            operation="blur",
            parameters={"radius": 6, "repeat": 5},
        ),
        PipelineStep(
            operation="sharpen",
            parameters={"factor": 2.5, "repeat": 3},
        ),
        PipelineStep(operation="edge_detect", parameters={}),
    ],
}