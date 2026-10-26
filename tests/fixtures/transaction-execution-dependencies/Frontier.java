package fixture;
public class Frontier {
    static class Nested { static void work() {} }
    public void run(boolean branch) { if (branch) Nested.work(); }
}
