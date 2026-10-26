package fixture;
public class Constructor {
    static class Nested { Nested() {} }
    public void run() { new Nested(); }
}
