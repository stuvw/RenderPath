# ---------------- SHADERS ----------------

VERTEX_SHADER_DEPTH = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec4 posScale; // Combined: x, y, z, and dx (scale)
layout(location = 5) in float quantity;
layout(location = 6) in float weight;

uniform mat4 projection;
uniform mat4 view;
uniform float globalScale;

out vec3 vWorldPosition;
flat out vec2 vDataValue;

void main() {
    // Manually calculate the world position: (local_pos * scale) + translation
    // globalScale is applied to the local vertex before the instance scale
    vec3 scaledPos = position * globalScale * posScale.w;
    vec3 worldPos = scaledPos + posScale.xyz;
    
    vWorldPosition = worldPos;
    
    // denominator is (scaleX * scaleY), which is (posScale.w * posScale.w)
    vDataValue = vec2(quantity * weight, weight) / (posScale.w * posScale.w);
    
    gl_Position = projection * view * vec4(worldPos, 1.0);
}
"""

FRAGMENT_SHADER_DEPTH = """
#version 330 core
in vec3 vWorldPosition;
flat in vec2 vDataValue;
uniform vec3 cameraPosition;
out vec4 FragColor;

void main() {
    float d = distance(vWorldPosition, cameraPosition);
    // Removing glFrontFacing fixes an issue, and I don't know why it was here to begin with...
    // float s = gl_FrontFacing ? 1.0 : -1.0;
    // float f = s * d;
    FragColor = vec4(d * vDataValue.x, d * vDataValue.y, 0.0, 1.0);
}
"""

SCREEN_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 position;
out vec2 vUv;
// Instead of: vUv = (position + 1.0) * 0.5;
// We now flip the frame here, removing one unnecessary call
void main() {
    vUv = vec2((position.x + 1.0) * 0.5, (1.0 - (position.y + 1.0) * 0.5)); 
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

SCREEN_FRAGMENT_SHADER = """
#version 330 core
in vec2 vUv;

uniform sampler2D depthTexture;
uniform sampler2D colormap;
uniform float minVal;
uniform float maxVal;

uniform vec4 underColor;
uniform vec4 overColor;
uniform vec4 badColor;

out vec4 FragColor;

void main() {
    vec2 data = texture(depthTexture, vUv).rg;
    float qw = data.r;
    float w  = data.g;

    if (w == 0.0) {
        FragColor = badColor;
        return;
    }

    const float INV_LOG10 = 0.4342944819;
    float depth = log(qw / w) * INV_LOG10;

    // Branchless tone mapping
    float t = (depth - minVal) / (maxVal - minVal);
    vec4 color = texture(colormap, vec2(clamp(t, 0.0, 1.0), 0.5));
    color = mix(underColor, color, step(0.0, t));
    color = mix(color, overColor, step(1.0, t));
    FragColor = color;
}
"""