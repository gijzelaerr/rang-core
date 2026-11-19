fn main() {
    let onnx = std::env::var("DL1_ONNX").expect("DL1_ONNX: the F3 ONNX file");
    println!("cargo:rerun-if-env-changed=DL1_ONNX");
    println!("cargo:rerun-if-changed={onnx}");
    let dst = std::path::Path::new(&std::env::var("OUT_DIR").unwrap()).join("f3.onnx");
    std::fs::copy(&onnx, &dst).unwrap();
    burn_onnx::ModelGen::new()
        .input(dst.to_str().unwrap())
        .out_dir("model/")
        .run_from_script();
}
