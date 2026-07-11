export const IMAGE_FILES = {
  small: "worker/examples/test.png",
  medium: "worker/examples/test.png",
  large: "worker/examples/test.png",
};

export const TASKS = {
  light_grayscale_small: {
    class: "light",
    imageSize: "small",
    pipeline: [{ operation: "grayscale", parameters: {} }],
  },
  light_rotate_small: {
    class: "light",
    imageSize: "small",
    pipeline: [{ operation: "rotate", parameters: { angle: 90 } }],
  },
  light_region_blur_medium: {
    class: "light",
    imageSize: "medium",
    pipeline: [
      {
        operation: "blur",
        parameters: {
          radius: 8,
          region: { x: 100, y: 100, width: 400, height: 300 },
        },
      },
    ],
  },
  medium_thumbnail_medium: {
    class: "medium",
    imageSize: "medium",
    pipeline: [
      { operation: "thumbnail", parameters: { width: 600, height: 600 } },
    ],
  },
  medium_edge_detect_medium: {
    class: "medium",
    imageSize: "medium",
    pipeline: [{ operation: "edge_detect", parameters: {} }],
  },
  heavy_blur_repeat_medium: {
    class: "heavy",
    imageSize: "medium",
    pipeline: [{ operation: "blur", parameters: { radius: 8, repeat: 10 } }],
  },
  heavy_mixed_pipeline_medium: {
    class: "heavy",
    imageSize: "medium",
    pipeline: [
      { operation: "thumbnail", parameters: { width: 1200, height: 1200 } },
      { operation: "blur", parameters: { radius: 6, repeat: 5 } },
      { operation: "sharpen", parameters: { factor: 2.5, repeat: 3 } },
      { operation: "edge_detect", parameters: {} },
    ],
  },
};

export const PROFILES = {
  light_only: [
    { task: "light_grayscale_small", weight: 40 },
    { task: "light_rotate_small", weight: 30 },
    { task: "light_region_blur_medium", weight: 30 },
  ],

  heavy_only: [
    { task: "heavy_blur_repeat_medium", weight: 70 },
    { task: "heavy_mixed_pipeline_medium", weight: 30 },
  ],

  representative_mixed: [
    { task: "light_grayscale_small", weight: 25 },
    { task: "light_rotate_small", weight: 20 },
    { task: "light_region_blur_medium", weight: 15 },
    { task: "medium_thumbnail_medium", weight: 15 },
    { task: "medium_edge_detect_medium", weight: 10 },
    { task: "heavy_blur_repeat_medium", weight: 10 },
    { task: "heavy_mixed_pipeline_medium", weight: 5 },
  ],

  stress_mixed: [
    { task: "light_grayscale_small", weight: 20 },
    { task: "medium_thumbnail_medium", weight: 20 },
    { task: "heavy_blur_repeat_medium", weight: 40 },
    { task: "heavy_mixed_pipeline_medium", weight: 20 },
  ],
};
