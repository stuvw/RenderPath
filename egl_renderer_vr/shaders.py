# ---------------- SHADERS ----------------

VERTEX_SHADER_DEPTH = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec4 posScale;
layout(location = 5) in float quantity;
layout(location = 6) in float weight;
uniform mat4 projection;
uniform mat4 view;
uniform float globalScale;
out vec3 vWorldPosition;
flat out vec2 vDataValue;
void main() {
    vec3 worldPos = (position * globalScale * posScale.w) + posScale.xyz;
    vWorldPosition = worldPos;
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
    FragColor = vec4(d * vDataValue.x, d * vDataValue.y, 0.0, 1.0);
}
"""

# Equirectangular Conversion Shader:  "unrolls" the cube faces into a 360 degree 2:1 projection.
EQUIRECT_FRAGMENT_SHADER = """
#version 330 core
in vec2 vUv;
uniform samplerCube cubemap;
uniform sampler2D colormap;
uniform float minVal;
uniform float maxVal;
uniform vec4 underColor;
uniform vec4 overColor;
uniform vec4 badColor;
out vec4 FragColor;

const float PI = 3.14159265359;
const float INV_LOG10 = 0.4342944819;

void main() {
    // flip vertical for ffmpeg (OpenGL is bottom-up, ffmpeg expects top-down)
    vec2 uv = vec2(vUv.x, 1.0 - vUv.y); 
    // Map UV to spherical coordinates
    float phi = (vUv.x * 2.0 - 1.0) * PI;
    float theta = (vUv.y * 2.0 - 1.0) * (PI / 2.0);

    // Convert to direction vector
    // vec3 dir = vec3(cos(theta) * sin(phi), sin(theta), cos(theta) * cos(phi));
    vec3 dir = vec3(cos(theta) * sin(-phi), sin(theta), cos(theta) * cos(-phi)); // negation fixes something ?
    vec2 data = texture(cubemap, dir).rg;
    
    float w = data.g;
    if (w == 0.0) {
        FragColor = badColor;
        return;
    }

    float depth = log(data.r / w) * INV_LOG10;
    float t = (depth - minVal) / (maxVal - minVal);
    
    vec4 color = texture(colormap, vec2(clamp(t, 0.0, 1.0), 0.5));
    color = mix(underColor, color, step(0.0, t));
    color = mix(color, overColor, step(1.0, t));
    FragColor = color;
}
"""

# Domemaster / azimuthal equidistant fisheye, the industry standard for fulldome.
DOMEMASTER_FRAGMENT_SHADER = """
#version 330 core
in vec2 vUv;
uniform samplerCube cubemap;
uniform sampler2D colormap;
uniform float minVal;
uniform float maxVal;
uniform vec4 underColor;
uniform vec4 overColor;
uniform vec4 badColor;

// Columns: right, up, forward — defines orientation of the dome's zenith
uniform mat3 domeBasis;

out vec4 FragColor;

const float PI = 3.14159265359;
const float INV_LOG10 = 0.4342944819;
const float HALF_PI = PI * 0.5;

void main() {
    // Map UV from [0,1] to [-1,1], Y-flipped to match OpenGL bottom-up readback
    vec2 uv = vec2(vUv.x * 2.0 - 1.0, 1.0 - vUv.y * 2.0);

    float r = length(uv);

    // Mask everything outside the dome circle
    if (r > 1.0) {
        FragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // Azimuthal equidistant: r maps linearly to angle from zenith
    float angle_from_zenith = r * HALF_PI;      // 0 at centre, PI/2 at rim
    float azimuth = atan(uv.y, uv.x);           // angle around the zenith axis

    // Build direction in the dome's local frame
    //   zenith component  = cos(angle_from_zenith)
    //   lateral component = sin(angle_from_zenith) * (cos/sin azimuth)
    float sin_a = sin(angle_from_zenith);
    float cos_a = cos(angle_from_zenith);

    // Local direction: x=right, y=up, z=forward(zenith)
    vec3 localDir = vec3(sin_a * cos(azimuth), sin_a * sin(azimuth), cos_a);

    // Rotate into world/cubemap space using the dome basis
    vec3 dir = domeBasis * localDir;

    // Sample the cubemap
    vec2 data = texture(cubemap, dir).rg;
    float w = data.g;
    if (w == 0.0) {
        FragColor = badColor;
        return;
    }
    

    float depth = log(data.r / w) * INV_LOG10;
    float t = (depth - minVal) / (maxVal - minVal);

    vec4 color = texture(colormap, vec2(clamp(t, 0.0, 1.0), 0.5));
    color = mix(underColor, color, step(0.0, t));
    color = mix(color, overColor, step(1.0, t));
    FragColor = color;
}
"""

SCREEN_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 position;
out vec2 vUv;
void main() {
    vUv = (position + 1.0) * 0.5; 
    gl_Position = vec4(position, 0.0, 1.0);
}
"""