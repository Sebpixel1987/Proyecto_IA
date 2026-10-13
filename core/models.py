from django.db import models

class PerfilCargo(models.Model):
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    # Aquí irían más campos técnicos del perfil...
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titulo

class Postulante(models.Model):
    nombre = models.CharField(max_length=100)
    rut = models.CharField(max_length=12, unique=True)
    cargo_postulado = models.ForeignKey(PerfilCargo, on_delete=models.CASCADE)
    
    # Checklist / Semáforo de documentos basado en validación[cite: 26]
    doc_carnet = models.BooleanField(default=False, verbose_name="Carnet")
    doc_titulo = models.BooleanField(default=False, verbose_name="Título")
    doc_cert_trabajo = models.BooleanField(default=False, verbose_name="Certificado de Trabajo")
    doc_cert_capacitacion = models.BooleanField(default=False, verbose_name="Certificados de Capacitación")

    def __str__(self):
        return f"{self.nombre} - {self.rut}"

    @property
    def semaforo_completitud(self):
        # Lógica sencilla para el Dashboard (Proyecto B)
        documentos = [self.doc_carnet, self.doc_titulo, self.doc_cert_trabajo, self.doc_cert_capacitacion]
        completos = sum(documentos)
        if completos == 4:
            return "VERDE"
        elif completos > 0:
            return "AMARILLO"
        return "ROJO"

class PautaEntrevistaIA(models.Model):
    """
    Molde para las propuestas de la IA, asegurando la estructura:
    2 técnicas, 2 de habilidad, 1 de motivación[cite: 26]
    """
    perfil = models.ForeignKey(PerfilCargo, on_delete=models.CASCADE)
    
    # Preguntas Técnicas (2)
    preg_tecnica_1 = models.TextField()
    preg_tecnica_2 = models.TextField()
    
    # Preguntas de Habilidad (2)
    preg_habilidad_1 = models.TextField()
    preg_habilidad_2 = models.TextField()
    
    # Pregunta de Motivación (1)
    preg_motivacion = models.TextField()
    
    fecha_generacion = models.DateTimeField(auto_now_add=True)
    aprobada_por_psicologa = models.BooleanField(default=False) # Cumplimiento de regla Human-in-the-Loop