#include "FlightTestPawn.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "UObject/ConstructorHelpers.h"

AFlightTestPawn::AFlightTestPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	Tags.Add(TEXT("FlightTestPawn"));
	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(60.f);
	Collision->SetCollisionProfileName(TEXT("Pawn"));
	RootComponent = Collision;
	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	Body->SetupAttachment(Collision);
	Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Body->SetRelativeScale3D(FVector(1.2f, 0.8f, 0.2f));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	if (CubeMesh.Succeeded())
	{
		Body->SetStaticMesh(CubeMesh.Object);
	}
}

void AFlightTestPawn::SetVirtualStick(float InThrottle, float Pitch, float Roll, float Yaw)
{
	Throttle = FMath::Clamp(InThrottle, 0.f, 1.f);
	Stick = FVector(FMath::Clamp(Pitch, -1.f, 1.f), FMath::Clamp(Roll, -1.f, 1.f), FMath::Clamp(Yaw, -1.f, 1.f));
}

void AFlightTestPawn::SetInitialSpeed(float CmPerSecond)
{
	Speed = FMath::Clamp(CmPerSecond, MinSpeed, MaxSpeed);
	Velocity = GetActorForwardVector() * Speed;
}

void AFlightTestPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.05f);
	// Rotacion en el marco propio del pawn (cuaterniones: los loops funcionan, sin gimbal lock).
	const FRotator Delta(Stick.X * PitchRate * Dt, Stick.Z * YawRate * Dt, Stick.Y * RollRate * Dt);
	AddActorLocalRotation(Delta.Quaternion());
	Speed = FMath::Clamp(Speed + (Throttle - 0.5f) * 2.f * Acceleration * Dt, MinSpeed, MaxSpeed);
	Velocity = GetActorForwardVector() * Speed;
	FHitResult Hit;
	AddActorWorldOffset(Velocity * Dt, true, &Hit);
	if (Hit.bBlockingHit)
	{
		// Deslizar a lo largo de lo que se golpeo.
		AddActorWorldOffset(FVector::VectorPlaneProject(Velocity * Dt * (1.f - Hit.Time), Hit.Normal), true);
	}
}
