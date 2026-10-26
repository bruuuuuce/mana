package fixture;
import java.util.List;
public class Parameterized {
    static class Nested { static void work() {} }
    public void run(List<String> values) { Nested.work(); }
}
