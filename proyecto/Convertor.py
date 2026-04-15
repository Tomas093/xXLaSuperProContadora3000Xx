import aspose.cad as cad

image = cad.Image.load("SAMPLE-24537-ASS-IE-GE-TP010-r00.dwg")
options = cad.imageoptions.DxfOptions()
image.save("archivo_real.dxf", options)