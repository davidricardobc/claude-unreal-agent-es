// Pawn volador minimo que cumple el contrato de flight-test-pilot. Sirve para probar la skill en un proyecto vacio, o
// como referencia para el propio pawn. Copiar a Source/<Modulo>/, reemplazar MYGAME_API por la macro del modulo,
// compilar con el editor cerrado y poner uno en un mapa (trae el tag FlightTestPawn).
// Verificado: compilado y volado por ue_flight_runner.py en un proyecto C++ en blanco de UE 5.8.4 (KitSmokeTest).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "FlightTestPawn.generated.h"

class USphereComponent;
class UStaticMeshComponent;

UCLASS()
class MYGAME_API AFlightTestPawn : public APawn
{
	GENERATED_BODY()

public:
	AFlightTestPawn();
	virtual void Tick(float DeltaSeconds) override;

	// ---- El contrato (la misma entrada para humanos, bots y maniobras guionadas) ----
	// Throttle 0..1, Pitch/Roll/Yaw -1..1 (pitch +1 = nariz arriba).
	UFUNCTION(BlueprintCallable, Category = "Flight Test")
	void SetVirtualStick(float Throttle, float Pitch, float Roll, float Yaw);

	// Se llama despues de que el script ubico el pawn: velocidad en cm/s.
	UFUNCTION(BlueprintCallable, Category = "Flight Test")
	void SetInitialSpeed(float CmPerSecond);

	// Un pawn que se mueve por desplazamientos no tiene velocidad de componente: informar la real (el runner la muestrea).
	virtual FVector GetVelocity() const override { return Velocity; }

	// ---- Parametros ajustables ----
	UPROPERTY(EditAnywhere, Category = "Flight Test")
	float MinSpeed = 1000.f;

	UPROPERTY(EditAnywhere, Category = "Flight Test")
	float MaxSpeed = 4000.f;

	// cm/s^2 con el acelerador a fondo (a medio acelerador mantiene la velocidad).
	UPROPERTY(EditAnywhere, Category = "Flight Test")
	float Acceleration = 1500.f;

	// Grados por segundo con el stick a fondo.
	UPROPERTY(EditAnywhere, Category = "Flight Test")
	float PitchRate = 90.f;

	UPROPERTY(EditAnywhere, Category = "Flight Test")
	float YawRate = 120.f;

	UPROPERTY(EditAnywhere, Category = "Flight Test")
	float RollRate = 180.f;

protected:
	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<USphereComponent> Collision;

	UPROPERTY(VisibleAnywhere, Category = "Components")
	TObjectPtr<UStaticMeshComponent> Body;

private:
	float Throttle = 0.5f;
	FVector Stick = FVector::ZeroVector; // X pitch, Y roll, Z yaw
	float Speed = 2000.f;
	FVector Velocity = FVector::ZeroVector;
};
