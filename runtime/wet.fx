// Subtle rain sheen for the city's road and paving textures. The gTun box
// reduces the wet response inside the covered river tunnel.
texture gTexture;
texture gScreen;
float gWet = 0.0;
float4 gTun = float4(0.0, 0.0, 0.0, 0.0);
float4x4 gWorldViewProjection : WORLDVIEWPROJECTION;
float4x4 gWorld : WORLD;

sampler BaseSampler = sampler_state
{
    Texture = (gTexture);
    MinFilter = Linear;
    MagFilter = Linear;
    MipFilter = Linear;
    AddressU = Wrap;
    AddressV = Wrap;
};

sampler ScreenSampler = sampler_state
{
    Texture = (gScreen);
    MinFilter = Linear;
    MagFilter = Linear;
    MipFilter = Linear;
    AddressU = Clamp;
    AddressV = Clamp;
};

struct VSInput
{
    float3 Position : POSITION0;
    float2 TexCoord : TEXCOORD0;
};

struct VSOutput
{
    float4 Position : POSITION0;
    float2 TexCoord : TEXCOORD0;
    float3 WorldPos : TEXCOORD1;
    float4 ScreenPos : TEXCOORD2;
};

struct PSInput
{
    float2 TexCoord : TEXCOORD0;
    float3 WorldPos : TEXCOORD1;
    float4 ScreenPos : TEXCOORD2;
};

VSOutput VSMain(VSInput input)
{
    VSOutput OUT;
    float4 localPosition = float4(input.Position, 1.0);
    OUT.Position = mul(localPosition, gWorldViewProjection);
    OUT.ScreenPos = OUT.Position;
    OUT.WorldPos = mul(localPosition, gWorld).xyz;
    OUT.TexCoord = input.TexCoord;
    return OUT;
}

float4 PSMain(PSInput input) : COLOR0
{
    float4 baseColor = tex2D(BaseSampler, input.TexCoord);
    float inTunnelX = 1.0 - step(7.0, abs(input.WorldPos.x - gTun.x));
    float inTunnelY = step(gTun.y, input.WorldPos.y) * (1.0 - step(gTun.z, input.WorldPos.y));
    float tunnelMask = saturate(inTunnelX * inTunnelY);
    float wetAmount = saturate(gWet) * lerp(1.0, 0.25, tunnelMask);
    float2 screenUV = input.ScreenPos.xy / max(abs(input.ScreenPos.w), 0.0001);
    screenUV = saturate(screenUV * float2(0.5, -0.5) + 0.5);
    float3 reflection = tex2D(ScreenSampler, screenUV).rgb;
    baseColor.rgb = lerp(baseColor.rgb, reflection, wetAmount * 0.08);
    baseColor.rgb *= lerp(1.0, 0.84, wetAmount);
    return baseColor;
}

technique tec0
{
    pass P0
    {
        VertexShader = compile vs_2_0 VSMain();
        PixelShader = compile ps_2_0 PSMain();
    }
}

technique fallback
{
}
