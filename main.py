"""Small executable smoke test for the initial project base."""

from datetime import datetime, timezone

from src.catalogo import CatalogoSismico
from src.dominio import Evento, Zona
from decimal import Decimal

def main() -> None:
    zonas = [Zona("Ciudad Central", 0, 500, 0, 500, True)]
    catalogo = CatalogoSismico(zonas, datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc))
    evento = Evento(
        identificador=10,
        magnitud=4.5,
        profundidad_hipocentro=30.0,
        x=100.0,
        y=100.0,
        ocurrencia="2026-09-07T10:00:00Z",
        revision=1,
        estaciones={"EST-01"},
    )
    evento2 = Evento(
        identificador=20,
        magnitud=5.0,
        profundidad_hipocentro=50.0,
        x=200.0,
        y=200.0,
        ocurrencia="2026-09-07T11:00:00Z",
        revision=1,
        estaciones={"EST-02"},
    )
    evento3 = Evento(
        identificador=30,
        magnitud=4.0,
        profundidad_hipocentro=50.0,
        x=300.0,
        y=300.0,
        ocurrencia="2026-09-07T11:30:00Z",
        revision=1,
        estaciones={"EST-03"},
    )
    catalogo.crear_evento(evento)
    catalogo.crear_evento(evento2)
    catalogo.crear_evento(evento3)
    print(f"{evento.clave()} -> prioridad {evento.prioridad}")
    print(f"{evento2.clave()} -> prioridad {evento2.prioridad}")
    print(f"{evento3.clave()} -> prioridad {evento3.prioridad}")

    print("Auditoria:", catalogo.avl.auditar())
    print("AVL:")
    for evento in catalogo.avl.inorden():
        print(evento.identificador)
    print("BST:")
    for evento in catalogo.bst.inorden():
        print(evento.identificador)

    print("Altura AVL:", catalogo.avl.altura())
    print("Altura BST:", catalogo.bst.altura())
    evento_buscado, examinados_avl = catalogo.avl.buscar_clave(evento.clave())
    print("Nodos examinados AVL:", examinados_avl)
    evento_buscado, examinados_bst = catalogo.bst.buscar_clave(evento.clave())
    print("Nodos examinados BST:", examinados_bst)
    evento_buscado, examinados_bst = catalogo.bst.buscar_clave(evento3.clave())
    print("Nodos examinados BST buscando evento3:", examinados_bst)
    evento_buscado, examinados_avl = catalogo.avl.buscar_clave(evento3.clave())
    print("Nodos examinados AVL buscando evento3:", examinados_avl)

    def menu():
        siguiente_id=1
        while True:
                
            print("Welcome")
            print("==================")
            print("1. Activar modo estres")
            print("2. Desactivar modo estres")
            print("3. crear evento ")
            print("4. Crear rafaga")
            print("0. Exit")

            option = int(input("Ingresar opcion: "))

            if option ==1:
                catalogo.activar_modo_estres()
                print("Modo estres: ", catalogo.modo_estres)

            if option == 2:
                giros = catalogo.desactivar_modo_estres()
                print("Giros: ",giros,", Modo estres: ",catalogo.modo_estres)

            if option == 3:
                catalogo.crear_evento(Evento(
                    identificador=siguiente_id,
                    magnitud=4.0,
                    profundidad_hipocentro=50.0,
                    x=300.0,
                    y=300.0,
                    ocurrencia="2026-09-07T11:30:00Z",
                    revision=1,
                    estaciones={"EST-03"},))
                siguiente_id +=1    
            
            if option ==4:
                numero=int(input("Numero de la rafaga entre 1-7"))
                for i in range(numero):
                    catalogo.crear_evento(Evento(
                        identificador=siguiente_id,
                        magnitud=4.0,
                        profundidad_hipocentro=50.0,
                        x=300.0,
                        y=300.0,
                        ocurrencia="2026-09-07T11:30:00Z",
                        revision=1,
                        estaciones={"EST-03"},))
                    siguiente_id +=1
                print(catalogo.avl.auditar().balanceado)        
            
            if option == 0:
                break
    menu()
    
if __name__ == "__main__":
    main()
